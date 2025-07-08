import cv2
import numpy as np

def detect_dial(image_gray):
    blurred = cv2.GaussianBlur(image_gray, (5, 5), 0)
    circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
                                param1=100, param2=30, minRadius=50, maxRadius=200)
    if circles is not None:
        circles = np.uint16(np.around(circles))
        x, y, r = circles[0, 0]
        return (x, y, r)
    return None

def automate_watch_dial_swap(src_path, dst_path, output_filename="final_watch_result.jpg"):
    src_img = cv2.imread(src_path)
    dst_img = cv2.imread(dst_path)
    if src_img is None or dst_img is None:
        print("Error loading images")
        return

    src_gray = cv2.cvtColor(src_img, cv2.COLOR_BGR2GRAY)
    dst_gray = cv2.cvtColor(dst_img, cv2.COLOR_BGR2GRAY)

    # Detect dials
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

    # Detect keypoints in dial region only
    orb = cv2.ORB_create(nfeatures=2000)
    kp1, des1 = orb.detectAndCompute(src_gray, mask=src_mask)
    kp2, des2 = orb.detectAndCompute(dst_gray, None)  # allow full dst for context
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(des1, des2, k=2)
    good_matches = [m for m, n in matches if m.distance < 0.75 * n.distance]
    print(f"Matches: {len(good_matches)}")

    if len(good_matches) < 10:
        print("Not enough matches")
        return

    src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    M, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    # Warp and shift to exact center alignment
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

    cv2.imwrite("feature_matches.jpg", cv2.drawMatches(src_img, kp1, dst_img, kp2, good_matches, None, flags=2))
    cv2.imwrite(output_filename, result)
    print(f"Saved final result as {output_filename}")

    cv2.imshow("Result", result)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    automate_watch_dial_swap("watch_white_bg.jpg", "watch_styled.jpg")
