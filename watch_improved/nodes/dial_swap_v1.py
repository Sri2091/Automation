# ComfyUI Node - uses circle(holoscircles) CV detection method and orb to feature match


import cv2
import numpy as np

class WatchDialSwapNode:
    """
    A ComfyUI node to automatically detect and swap the dial from a source watch image
    onto a destination watch image, with user-controlled inset to exclude the bezel.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "source_image": ("IMAGE",),
                "destination_image": ("IMAGE",),
                "dial_inset_pixels": ("INT", {
                    "default": 10, 
                    "min": 0, 
                    "max": 100, 
                    "step": 1,
                    "display": "slider"
                }),
                "feather_amount": ("INT", {
                    "default": 15, 
                    "min": 1, 
                    "max": 51, 
                    "step": 2
                }),
                "n_features": ("INT", {
                    "default": 2000, 
                    "min": 500, 
                    "max": 5000, 
                    "step": 100
                }),
                "match_threshold": ("FLOAT", {
                    "default": 0.75,
                    "min": 0.1,
                    "max": 1.0,
                    "step": 0.05
                }),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("final_image", "feature_matches_image")
    FUNCTION = "swap_dial"
    CATEGORY = "Image/Processing"

    def tensor_to_cv2(self, tensor_img):
        """Converts a ComfyUI image tensor to an OpenCV image (numpy array)."""
        img_np = tensor_img.squeeze(0).cpu().numpy()
        img_np_uint8 = (img_np * 255).astype(np.uint8)
        img_cv2 = cv2.cvtColor(img_np_uint8, cv2.COLOR_RGB2BGR)
        return img_cv2

    def cv2_to_tensor(self, cv2_img):
        """Converts an OpenCV image (numpy array) to a ComfyUI image tensor."""
        img_rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
        img_float = img_rgb.astype(np.float32) / 255.0
        tensor_img = torch.from_numpy(img_float).unsqueeze(0)
        return tensor_img

    def detect_dial(self, image_gray):
        """Detects the most prominent circular feature (likely bezel or dial edge)."""
        blurred = cv2.GaussianBlur(image_gray, (5, 5), 0)
        h, w = image_gray.shape
        max_r = int(min(h, w) * 0.5) 
        min_r = int(min(h, w) * 0.1)
        
        circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=h//2,
                                   param1=100, param2=30, minRadius=min_r, maxRadius=max_r)
        if circles is not None:
            circles = np.uint16(np.around(circles))
            x, y, r = circles[0, 0]
            return (x, y, r)
        return None

    def swap_dial(self, source_image, destination_image, dial_inset_pixels, feather_amount, n_features, match_threshold):
        src_img = self.tensor_to_cv2(source_image)
        dst_img = self.tensor_to_cv2(destination_image)
        
        if feather_amount % 2 == 0:
            feather_amount += 1

        src_gray = cv2.cvtColor(src_img, cv2.COLOR_BGR2GRAY)
        dst_gray = cv2.cvtColor(dst_img, cv2.COLOR_BGR2GRAY)

        # 1. Detect source circle
        src_circle = self.detect_dial(src_gray)
        if not src_circle:
            print("WatchDialSwapNode: Could not detect circle in the SOURCE image. Aborting.")
            black_img = np.zeros_like(dst_img)
            return (self.cv2_to_tensor(dst_img), self.cv2_to_tensor(black_img))

        # 2. Create the source mask, APPLYING THE INSET
        src_x, src_y, src_r = src_circle
        # Reduce the radius by the user-defined inset value to exclude the bezel
        inset_radius = src_r - dial_inset_pixels
        if inset_radius < 5: # Safety check to prevent negative or zero radius
            print(f"WatchDialSwapNode: Warning - Inset of {dial_inset_pixels} is too large. Clamping radius to 5 pixels.")
            inset_radius = 5
            
        src_mask = np.zeros(src_gray.shape, dtype=np.uint8)
        cv2.circle(src_mask, (src_x, src_y), inset_radius, 255, -1)

        # 3. Detect keypoints using the new, smaller mask
        orb = cv2.ORB_create(nfeatures=n_features)
        kp1, des1 = orb.detectAndCompute(src_gray, mask=src_mask)
        kp2, des2 = orb.detectAndCompute(dst_gray, None)
        
        if des1 is None or des2 is None:
            print("WatchDialSwapNode: No features found within the inset dial area.")
            black_img = np.zeros_like(dst_img)
            return (self.cv2_to_tensor(dst_img), self.cv2_to_tensor(black_img))

        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(des1, des2, k=2)
        
        good_matches = []
        if matches and len(matches) > 0 and len(matches[0]) == 2:
            good_matches = [m for m, n in matches if m.distance < match_threshold * n.distance]
        
        print(f"WatchDialSwapNode: Found {len(good_matches)} good matches.")
        matches_img = cv2.drawMatches(src_img, kp1, dst_img, kp2, good_matches, None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)

        if len(good_matches) < 10:
            print("WatchDialSwapNode: Not enough matches found. Try reducing the inset or adjusting match parameters.")
            return (self.cv2_to_tensor(dst_img), self.cv2_to_tensor(matches_img))

        # 4. Find Homography and Warp
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        M, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        if M is None:
            print("WatchDialSwapNode: Could not compute homography.")
            return (self.cv2_to_tensor(dst_img), self.cv2_to_tensor(matches_img))

        # 5. Warp the source image and mask
        h, w = dst_img.shape[:2]
        warped_src = cv2.warpPerspective(src_img, M, (w, h))
        warped_mask = cv2.warpPerspective(src_mask, M, (w, h))

        # 6. Feather the warped mask and blend
        feathered_mask = cv2.GaussianBlur(warped_mask, (feather_amount, feather_amount), 0)
        alpha = feathered_mask.astype(float) / 255.0
        alpha_3ch = cv2.merge([alpha] * 3)

        foreground = warped_src.astype(float)
        background = dst_img.astype(float)
        blended = cv2.multiply(alpha_3ch, foreground) + cv2.multiply(1 - alpha_3ch, background)
        result = np.clip(blended, 0, 255).astype(np.uint8)

        return (self.cv2_to_tensor(result), self.cv2_to_tensor(matches_img))

# ComfyUI Node Registration
NODE_CLASS_MAPPINGS = {
    "WatchDialSwap": WatchDialSwapNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WatchDialSwap": "Watch Dial Swap"
}