import os
import glob
from pathlib import Path

def rename_images_in_folder(folder_path, prefix="cosmos"):
    """
    Force rename all image files in a folder to cosmos_1, cosmos_2, etc.
    """
    # Common image extensions
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.tiff', '*.webp']
    
    # Get all image files
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(folder_path, ext), recursive=False))
        image_files.extend(glob.glob(os.path.join(folder_path, ext.upper()), recursive=False))
    
    # Sort files for consistent ordering
    image_files.sort()
    
    if not image_files:
        print("No image files found.")
        return
    
    print(f"Renaming {len(image_files)} files...")
    
    # First pass: rename to temporary names to avoid conflicts
    temp_files = []
    for i, old_path in enumerate(image_files):
        temp_name = f"temp_rename_{i}_{os.path.basename(old_path)}"
        temp_path = os.path.join(folder_path, temp_name)
        os.rename(old_path, temp_path)
        temp_files.append(temp_path)
    
    # Second pass: rename to final names
    for i, temp_path in enumerate(temp_files):
        file_ext = Path(temp_path).suffix.lower()
        new_filename = f"{prefix}_{i+1}{file_ext}"
        new_path = os.path.join(folder_path, new_filename)
        os.rename(temp_path, new_path)
        print(f"Renamed to: {new_filename}")

# Usage
folder_path = input("Folder path: ").strip().strip('"\'')
prefix = input("Prefix (default: cosmos): ").strip() or "cosmos"

rename_images_in_folder(folder_path, prefix)