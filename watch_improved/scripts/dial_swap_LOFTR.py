import cv2
import numpy as np
import torch
import kornia as K
import kornia.feature as KF

# --- 1. LOFTR MODEL SETUP ---

# Configure PyTorch Device (GPU/CPU)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {DEVICE}")
if not torch.cuda.is_available():
    print("WARNING: CUDA not found. LoFTR model will run on the CPU and will be very slow.")

# Load the LoFTR Deep Learning model onto the device
try:
    print("Loading LoFTR model (this may download weights on the first run)...")
    LOFTR_MODEL = KF.LoFTR(pretrained='outdoor').to(DEVICE).eval()
    print("LoFTR model loaded successfully.")
except Exception as e:
    print(f"FATAL: Failed to load LoFTR model: {e}")
    print("Please ensure PyTorch, Kornia, and CUDA are installed correctly.")
    exit()

# --- 2. CORE FUNCTIONS ---

def detect_dial(image_gray):
    # This function is unchanged
    blurred = cv2.GaussianBlur(image_gray, (5, 5), 0)
    circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
                                param1=100, param2=30, minRadius=50, maxRadius=200)
    if circles is not None:
        circles = np.uint16(np.around(circles))
        x, y, r = circles[0, 0]
        return (x, y, r)
    return None

# =============================================================================
# NEW FUNCTION TO VISUALIZE LoFTR MATCHES
# =============================================================================
def draw_loftr_matches(src_img, dst_img, src_pts, dst_pts):
    """
    Draws lines connecting matched points between two images.
    """
    # Create a new image to display the matches
    h1, w1 = src_img.shape[:2]
    h2, w2 = dst_img.shape[:2]
    vis = np.zeros((max(h1, h2), w1 + w2, 3), dtype='uint8')
    vis[:h1, :w1] = src_img
    vis[:h2, w1:] = dst_img

    # Draw the lines
    for p1, p2 in zip(src_pts, dst_pts):
        pt1 = (int(round(p1[0])), int(round(p1[1])))
        # The x-coordinate for the destination point needs to be shifted by the width of the source image
        pt2 = (int(round(p2[0]) + w1), int(round(p2[1])))
        
        # Draw a line and circles at the points
        color = tuple(np.random.randint(0, 255, 3).tolist())
        cv2.line(vis, pt1, pt2, color, 1)
        cv2.circle(vis, pt1, 3, color, -1)
        cv2.circle(vis, pt2, 3, color, -1)
        
    return vis
# =============================================================================

def extract_and_match_features_loftr(img0_gray, img1_gray, mask0=None):
    """
    Uses the LoFTR deep learning model to find and match features.
    """
    print("Extracting and matching features with LoFTR model...")
    timg0 = K.image_to_tensor(img0_gray, False).float() / 255.
    timg0 = timg0.to(DEVICE)
    timg1 = K.image_to_tensor(img1_gray, False).float() / 255.
    timg1 = timg1.to(DEVICE)

    if mask0 is not None:
        tmask0 = torch.from_numpy(mask0).unsqueeze(0).unsqueeze(0).to(DEVICE)
        timg0[tmask0 == 0] = 0.0

    input_dict = {"image0": timg0, "image1": timg1}
    with torch.no_grad():
        correspondences = LOFTR_MODEL(input_dict)

    mkpts0 = correspondences['keypoints0'].cpu().numpy()
    mkpts1 = correspondences['keypoints1'].cpu().numpy()
    confidence = correspondences['confidence'].cpu().numpy()
    
    confidence_threshold = 0.8
    good_indices = np.where(confidence > confidence_threshold)[0]
    
    if len(good_indices) == 0:
        print("-> LoFTR found no confident matches.")
        return None, None

    print(f"-> LoFTR found {len(good_indices)} confident matches.")
    src_pts = mkpts0[good_indices]
    dst_pts = mkpts1[good_indices]
    
    return src_pts, dst_pts

def automate_watch_dial_swap(src_path, dst_path, output_filename="final_watch_result.jpg"):
    src_img = cv2.imread(src_path)
    dst_img = cv2.imread(dst_path)
    if src_img is None or dst_img is None:
        print("Error loading images")
        return

    src_gray = cv2.cvtColor(src_img, cv2.COLOR_BGR2GRAY)
    dst_gray = cv2.cvtColor(dst_img, cv2.COLOR_BGR2GRAY)

    # Detect dials using the original HoughCircles method
    src_circle = detect_dial(src_gray)
    dst_circle = detect_dial(dst_gray)
    if not src_circle or not dst_circle:
        print("Could not detect circles in one or both images.")
        return
    src_x, src_y, src_r = src_circle
    dst_x, dst_y, dst_r = dst_circle

    # Create source mask
    src_mask = np.zeros(src_gray.shape, dtype=np.uint8)
    cv2.circle(src_mask, (src_x, src_y), src_r, 255, -1)

    # Feature Matching with LoFTR
    src_pts, dst_pts = extract_and_match_features_loftr(src_gray, dst_gray, src_mask)

    if src_pts is None or len(src_pts) < 10:
        print("Not enough matches found by LoFTR. Cannot proceed.")
        return

    # =============================================================================
    # MODIFIED SECTION: SAVE THE VISUALIZATION
    # =============================================================================
    print("Saving feature match visualization to 'feature_matches.jpg'")
    matches_img = draw_loftr_matches(src_img, dst_img, src_pts, dst_pts)
    cv2.imwrite("feature_matches.jpg", matches_img)
    # =============================================================================
    
    # Reshape points for findHomography
    src_pts_reshaped = src_pts.reshape(-1, 1, 2)
    dst_pts_reshaped = dst_pts.reshape(-1, 1, 2)
    M, _ = cv2.findHomography(src_pts_reshaped, dst_pts_reshaped, cv2.RANSAC, 5.0)
    if M is None:
        print("Could not compute a valid homography matrix. Aborting.")
        return

    # The rest of the script is unchanged
    h, w = dst_img.shape[:2]
    warped_src = cv2.warpPerspective(src_img, M, (w, h))
    warped_mask = cv2.warpPerspective(src_mask, M, (w, h))

    # Compute centroid of warped source
    moments = cv2.moments(warped_mask)
    if moments["m00"] != 0:
        warped_cx = int(moments["m10"] / moments["m00"])
        warped_cy = int(moments["m01"] / moments["m00"])
    else:
        print("Warped mask has no area.")
        return

    dx = dst_x - warped_cx
    dy = dst_y - warped_cy

    # Affine shift to correct final center alignment
    shift_matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    shifted_src = cv2.warpAffine(warped_src, shift_matrix, (w, h))
    shifted_mask = cv2.warpAffine(warped_mask, shift_matrix, (w, h))

    # Feather mask
    kernel = np.ones((3, 3), np.uint8)
    eroded_mask = cv2.erode(shifted_mask, kernel, iterations=2)
    feathered = cv2.GaussianBlur(eroded_mask, (15, 15), 0)
    alpha = feathered.astype(float) / 255.0
    alpha_3ch = cv2.merge([alpha] * 3)

    foreground = shifted_src.astype(float)
    background = dst_img.astype(float)
    blended = cv2.multiply(alpha_3ch, foreground) + cv2.multiply(1 - alpha_3ch, background)
    result = blended.astype(np.uint8)

    cv2.imwrite(output_filename, result)
    print(f"Saved final result as {output_filename}")

    cv2.imshow("Result", result)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    automate_watch_dial_swap("watch_white_bg.jpg", "watch_styled.jpg")