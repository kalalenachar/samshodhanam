import os
import glob
from PIL import Image

def generate_thumbnails():
    # Base directory is the directory where this script is located (project root)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    uploads_dir = os.path.join(base_dir, 'katha', 'uploads')
    
    if not os.path.exists(uploads_dir):
        print(f"Directory {uploads_dir} does not exist.")
        return
        
    pattern = os.path.join(uploads_dir, 'cov_*')
    cover_files = glob.glob(pattern)
    print(f"Found {len(cover_files)} cover files in {uploads_dir}.")
    
    success_count = 0
    skipped_count = 0
    error_count = 0
    
    for file_path in cover_files:
        filename = os.path.basename(file_path)
        # Skip if it's already a thumbnail or a non-image file
        if filename.startswith('thumb_'):
            continue
            
        thumb_filename = f"thumb_{filename}"
        thumb_path = os.path.join(uploads_dir, thumb_filename)
        
        if os.path.exists(thumb_path):
            print(f"Thumbnail already exists for {filename}, skipping.")
            skipped_count += 1
            continue
            
        print(f"Generating thumbnail for {filename}...")
        try:
            with Image.open(file_path) as img:
                # Resize keeping aspect ratio
                img.thumbnail((400, 400))
                # Save thumbnail in original format
                img.save(thumb_path, format=img.format)
                print(f"Successfully saved {thumb_filename}")
                success_count += 1
        except Exception as e:
            print(f"Error generating thumbnail for {filename}: {e}")
            error_count += 1
            
    print(f"\nMigration complete: {success_count} generated, {skipped_count} skipped, {error_count} errors.")

if __name__ == '__main__':
    generate_thumbnails()
