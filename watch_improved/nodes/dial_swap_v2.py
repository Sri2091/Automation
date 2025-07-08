# ComfyUI Node - uses Loftr to swap dials, outputs mask, feature map, final image



import torch
import numpy as np
import cv2
import kornia as K
import kornia.feature as KF
import comfy.model_management
import comfy.utils

# Tensor to CV2 Image (and back) utilities
def tensor_to_cv2(tensor: torch.Tensor) -> np.ndarray:
    """Converts a ComfyUI-style tensor (B, H, W, C) [0,1] to an OpenCV-style BGR uint8 image (H, W, C) [0,255]."""
    img_tensor = tensor[0]
    img_np = np.clip(255. * img_tensor.cpu().numpy(), 0, 255).astype(np.uint8)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    return img_bgr

def cv2_to_tensor(image: np.ndarray) -> torch.Tensor:
    """Converts an OpenCV-style BGR uint8 image (H, W, C) [0,255] to a ComfyUI-style tensor (B, H, W, C) [0,1]."""
    img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    img_float = img_rgb.astype(np.float32) / 255.0
    tensor = torch.from_numpy(img_float).unsqueeze(0)
    return tensor

class LoFTRWatchDialSwapperV2:
    def __init__(self):
        self.device = comfy.model_management.get_torch_device()
        self.loftr = None
        print("Initializing LoFTR Watch Dial Swapper V2 Node")

    def _load_model(self):
        """Loads the LoFTR model onto the correct device if it hasn't been loaded yet."""
        if self.loftr is None:
            try:
                print("Loading LoFTR model (this may download weights on the first run)...")
                pbar = comfy.utils.ProgressBar(1)
                self.loftr = KF.LoFTR(pretrained='outdoor').to(self.device).eval()
                pbar.update(1)
                print("LoFTR model loaded successfully.")
            except Exception as e:
                print(f"FATAL: Failed to load LoFTR model: {e}")
                raise e

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "source_image": ("IMAGE",),
                "destination_image": ("IMAGE",),
                "try_lower_confidence": ("BOOLEAN", {"default": True, "label_on": "auto_confidence", "label_off": "manual_confidence"}),
                "confidence_threshold": ("FLOAT", {"default": 0.8, "min": 0.1, "max": 1.0, "step": 0.05}),
                "feather_erosion_strength": ("INT", {"default": 2, "min": 0, "max": 10, "step": 1}),
                "feather_blur_size": ("INT", {"default": 15, "min": 1, "max": 99, "step": 2}),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "MASK")
    RETURN_NAMES = ("final_blended_image", "feature_match_image", "transformed_dial_image", "transformed_dial_mask")
    FUNCTION = "swap_dial"
    CATEGORY = "Image/Swapping"

    # --- CORE FUNCTIONS ---

    def _detect_dial(self, image_gray: np.ndarray):
        """Detects the largest circular dial in a grayscale image."""
        blurred = cv2.GaussianBlur(image_gray, (5, 5), 0)
        # Make maxRadius dependent on image size to be more robust
        max_radius = min(image_gray.shape) // 2
        circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
                                   param1=100, param2=30, minRadius=50, maxRadius=max_radius)
        if circles is not None:
            circles = np.uint16(np.around(circles))
            x, y, r = circles[0, 0]
            return (x, y, r)
        return None

    def _draw_loftr_matches(self, src_img, dst_img, src_pts, dst_pts):
        """Draws lines connecting matched points between two images."""
        h1, w1 = src_img.shape[:2]
        h2, w2 = dst_img.shape[:2]
        vis = np.zeros((max(h1, h2), w1 + w2, 3), dtype='uint8')
        vis[:h1, :w1] = src_img
        vis[:h2, w1:] = dst_img

        if src_pts is None or dst_pts is None: return vis

        for p1, p2 in zip(src_pts, dst_pts):
            pt1 = (int(round(p1[0])), int(round(p1[1])))
            pt2 = (int(round(p2[0]) + w1), int(round(p2[1])))
            color = tuple(np.random.randint(0, 255, 3).tolist())
            cv2.line(vis, pt1, pt2, color, 1)
        return vis

    def _extract_and_match_features_loftr(self, img0_gray, img1_gray, confidence_threshold, try_lower_confidence, mask0=None):
        """Uses the LoFTR model to find features, with robust thresholding."""
        print("Extracting and matching features with LoFTR...")
        timg0 = K.image_to_tensor(img0_gray, False).float() / 255.
        timg0 = timg0.to(self.device)
        timg1 = K.image_to_tensor(img1_gray, False).float() / 255.
        timg1 = timg1.to(self.device)

        if mask0 is not None:
            tmask0 = torch.from_numpy(mask0).unsqueeze(0).unsqueeze(0).to(self.device)
            timg0[tmask0 == 0] = 0.0

        input_dict = {"image0": timg0, "image1": timg1}
        with torch.no_grad():
            correspondences = self.loftr(input_dict)

        mkpts0 = correspondences['keypoints0'].cpu().numpy()
        mkpts1 = correspondences['keypoints1'].cpu().numpy()
        confidence = correspondences['confidence'].cpu().numpy()

        threshold_list = [0.8, 0.7, 0.6, 0.5] if try_lower_confidence else [confidence_threshold]

        for thresh in threshold_list:
            good_indices = np.where(confidence > thresh)[0]
            if len(good_indices) >= 10:
                print(f"-> LoFTR found {len(good_indices)} confident matches at threshold {thresh}.")
                return mkpts0[good_indices], mkpts1[good_indices]

        print(f"-> LoFTR found insufficient confident matches after trying thresholds: {threshold_list}.")
        return None, None

    def swap_dial(self, source_image, destination_image, try_lower_confidence, confidence_threshold, feather_erosion_strength, feather_blur_size):
        self._load_model()

        src_img = tensor_to_cv2(source_image)
        dst_img = tensor_to_cv2(destination_image)
        src_gray = cv2.cvtColor(src_img, cv2.COLOR_BGR2GRAY)
        dst_gray = cv2.cvtColor(dst_img, cv2.COLOR_BGR2GRAY)

        # Create empty/fallback outputs for error cases
        h, w = dst_img.shape[:2]
        empty_matches = self._draw_loftr_matches(src_img, dst_img, None, None)
        empty_rgb_tensor = torch.zeros_like(destination_image)
        empty_mask_tensor = torch.zeros((1, h, w), dtype=torch.float32, device=self.device)

        # Detect dials
        src_circle = self._detect_dial(src_gray)
        dst_circle = self._detect_dial(dst_gray)

        # CRITICAL FIX: Use 'is None' for robust check
        if src_circle is None or dst_circle is None:
            print("ERROR: Could not detect circles in one or both images. Aborting.")
            return (destination_image, cv2_to_tensor(empty_matches), empty_rgb_tensor, empty_mask_tensor)

        src_x, src_y, src_r = src_circle
        dst_x, dst_y, dst_r = dst_circle

        src_mask = np.zeros(src_gray.shape, dtype=np.uint8)
        cv2.circle(src_mask, (src_x, src_y), src_r, 255, -1)

        # Feature Matching with LoFTR (with improved logic)
        src_pts, dst_pts = self._extract_and_match_features_loftr(src_gray, dst_gray, confidence_threshold, try_lower_confidence, src_mask)
        
        matches_img_cv2 = self._draw_loftr_matches(src_img, dst_img, src_pts, dst_pts)
        matches_tensor = cv2_to_tensor(matches_img_cv2)

        if src_pts is None or len(src_pts) < 10:
            print("ERROR: Not enough matches found by LoFTR. Cannot proceed with swap.")
            return (destination_image, matches_tensor, empty_rgb_tensor, empty_mask_tensor)

        M, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if M is None:
            print("ERROR: Could not compute a valid homography matrix. Aborting.")
            return (destination_image, matches_tensor, empty_rgb_tensor, empty_mask_tensor)

        # Warp the source image and its mask
        warped_src = cv2.warpPerspective(src_img, M, (w, h))
        warped_mask = cv2.warpPerspective(src_mask, M, (w, h))

        # Center Alignment Correction
        moments = cv2.moments(warped_mask)
        if moments["m00"] != 0:
            warped_cx, warped_cy = int(moments["m10"] / moments["m00"]), int(moments["m01"] / moments["m00"])
        else:
            print("Warning: Warped mask has no area, skipping final alignment.")
            warped_cx, warped_cy = dst_x, dst_y

        dx, dy = dst_x - warped_cx, dst_y - warped_cy
        shift_matrix = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted_src = cv2.warpAffine(warped_src, shift_matrix, (w, h))
        shifted_mask = cv2.warpAffine(warped_mask, shift_matrix, (w, h))
        
        # --- NEW OUTPUTS ---
        # The transformed dial (RGB part) and its mask (alpha part)
        transformed_dial_image_tensor = cv2_to_tensor(shifted_src)
        transformed_dial_mask_tensor = torch.from_numpy(shifted_mask.astype(np.float32) / 255.0).unsqueeze(0)

        # Blending with Feathered Mask
        if feather_erosion_strength > 0:
            kernel = np.ones((3, 3), np.uint8)
            eroded_mask = cv2.erode(shifted_mask, kernel, iterations=feather_erosion_strength)
        else:
            eroded_mask = shifted_mask
            
        ksize = feather_blur_size if feather_blur_size % 2 != 0 else feather_blur_size + 1
        feathered_mask = cv2.GaussianBlur(eroded_mask, (ksize, ksize), 0)
        
        alpha_3ch = cv2.cvtColor(feathered_mask, cv2.COLOR_GRAY2BGR).astype(float) / 255.0
        
        blended = cv2.multiply(alpha_3ch, shifted_src.astype(float)) + cv2.multiply(1 - alpha_3ch, dst_img.astype(float))
        result_img_cv2 = blended.astype(np.uint8)

        final_blended_tensor = cv2_to_tensor(result_img_cv2)

        return (final_blended_tensor, matches_tensor, transformed_dial_image_tensor, transformed_dial_mask_tensor)

# --- ComfyUI Node Registration ---
NODE_CLASS_MAPPINGS = {
    "LoFTRWatchDialSwapperV2": LoFTRWatchDialSwapperV2
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoFTRWatchDialSwapperV2": "LoFTR Watch Dial Swapper V2"
}