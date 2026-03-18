#!/usr/bin/env python3
"""
remove_watermark.py
-------------------
Preprocess scanned math documents to remove teacher-name watermarks/signatures
that appear as semi-transparent diagonal text in the background.

Works on both local files and GCS blobs.  Cleaned images are saved alongside
the originals (or to a separate output directory) so that digitize.py can
process them without watermark interference.

Approach:
  1. Convert to grayscale
  2. Apply adaptive thresholding to separate dark foreground (math content)
     from lighter background (watermark)
  3. Use morphological operations to clean residual watermark artefacts
  4. Reconstruct a clean binary image suitable for OCR

Usage:
  # Clean a single file
  python remove_watermark.py --input scan.png --output clean.png

  # Batch-clean a folder of scans
  python remove_watermark.py --input_dir ./raw_scans --output_dir ./clean_scans

  # Batch-clean with custom threshold (lower = more aggressive removal)
  python remove_watermark.py --input_dir ./raw_scans --output_dir ./clean_scans --threshold 180

  # Download from GCS, clean, re-upload
  python remove_watermark.py --gcs_input gs://bucket/raw/ --gcs_output gs://bucket/clean/
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


def remove_watermark(
    image: np.ndarray,
    threshold: int = 160,
    morph_kernel_size: int = 2,
) -> np.ndarray:
    """
    Remove semi-transparent watermark text from a scanned document image.

    The watermark is typically lighter gray text overlaid on the page.  Real
    math content (printed text, formulas) is darker.  We exploit this contrast
    difference.

    Parameters
    ----------
    image : np.ndarray
        Input image (BGR or grayscale).
    threshold : int
        Pixel intensity threshold (0-255).  Pixels *above* this value are
        considered background/watermark and set to white.  Lower values are
        more aggressive (remove more).  Default 160 works well for typical
        gray watermarks on white paper.
    morph_kernel_size : int
        Size of the morphological kernel used to clean small artefacts.

    Returns
    -------
    np.ndarray
        Cleaned image (same number of channels as input).
    """
    # Convert to grayscale for processing
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        is_color = True
    else:
        gray = image.copy()
        is_color = False

    # Step 1: Simple threshold to kill the watermark
    # Watermark pixels are lighter (higher intensity) than real content
    # Set everything above threshold to white (background)
    _, binary_mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    # Step 2: Adaptive threshold to recover math content that may overlap
    # with watermark regions.  Adaptive thresholding looks at local contrast,
    # so dark strokes survive even when sitting on a gray watermark.
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
        blockSize=21, C=15,
    )

    # Step 3: Combine — a pixel is foreground (black) only if BOTH methods
    # agree it's dark enough.  This removes watermark while preserving content.
    combined = cv2.bitwise_or(binary_mask, adaptive)

    # Step 4: Morphological closing to fill tiny gaps in text strokes
    if morph_kernel_size > 0:
        kernel = np.ones((morph_kernel_size, morph_kernel_size), np.uint8)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

    # Step 5: Small connected-component removal to clean isolated watermark
    # fragments that survived thresholding
    combined = _remove_small_components(combined, min_area=30)

    if is_color:
        # Apply the binary mask back to the original color image
        # Where combined is white (255) -> keep white; where black -> keep original
        result = image.copy()
        result[combined == 255] = 255
        return result
    else:
        return combined


def _remove_small_components(binary_img: np.ndarray, min_area: int = 30) -> np.ndarray:
    """Remove small dark connected components (likely watermark remnants)."""
    # Invert: we want to find dark (foreground) components
    inverted = cv2.bitwise_not(binary_img)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)

    # Create a mask of components to remove (too small = watermark noise)
    mask = np.zeros_like(inverted)
    for i in range(1, num_labels):  # skip background (label 0)
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            mask[labels == i] = 255

    # Invert back: foreground=black on white background
    return cv2.bitwise_not(mask)


def process_file(
    input_path: str,
    output_path: str,
    threshold: int = 160,
    morph_kernel_size: int = 2,
) -> bool:
    """Process a single image file. Returns True on success."""
    image = cv2.imread(input_path, cv2.IMREAD_COLOR)
    if image is None:
        print(f"  ERROR: Could not read {input_path}", file=sys.stderr)
        return False

    cleaned = remove_watermark(image, threshold=threshold, morph_kernel_size=morph_kernel_size)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    cv2.imwrite(output_path, cleaned)
    print(f"  OK: {input_path} -> {output_path}")
    return True


def process_directory(
    input_dir: str,
    output_dir: str,
    threshold: int = 160,
    morph_kernel_size: int = 2,
) -> tuple:
    """Batch-process all images in a directory. Returns (success_count, fail_count)."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    ok, fail = 0, 0

    for fpath in sorted(input_path.rglob("*")):
        if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel = fpath.relative_to(input_path)
        out = output_path / rel
        if process_file(str(fpath), str(out), threshold, morph_kernel_size):
            ok += 1
        else:
            fail += 1

    return ok, fail


def process_gcs(
    gcs_input: str,
    gcs_output: str,
    threshold: int = 160,
    morph_kernel_size: int = 2,
) -> tuple:
    """Download images from GCS, clean, re-upload to a different prefix."""
    from google.cloud import storage as gcs

    def parse_gs(uri):
        assert uri.startswith("gs://"), f"Not a gs:// URI: {uri}"
        parts = uri[5:].split("/", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    src_bucket_name, src_prefix = parse_gs(gcs_input)
    dst_bucket_name, dst_prefix = parse_gs(gcs_output)

    client = gcs.Client()
    src_bucket = client.bucket(src_bucket_name)
    dst_bucket = client.bucket(dst_bucket_name)

    ok, fail = 0, 0

    for blob in src_bucket.list_blobs(prefix=src_prefix):
        ext = os.path.splitext(blob.name)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        print(f"  Processing: gs://{src_bucket_name}/{blob.name}")

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_in:
            blob.download_to_filename(tmp_in.name)
            tmp_out = tmp_in.name + ".clean" + ext

            if process_file(tmp_in.name, tmp_out, threshold, morph_kernel_size):
                # Upload cleaned file
                rel_path = blob.name[len(src_prefix):].lstrip("/")
                dst_name = os.path.join(dst_prefix, rel_path).replace("\\", "/")
                dst_blob = dst_bucket.blob(dst_name)
                dst_blob.upload_from_filename(tmp_out)
                print(f"  Uploaded: gs://{dst_bucket_name}/{dst_name}")
                ok += 1
            else:
                fail += 1

            # Clean up temp files
            for f in [tmp_in.name, tmp_out]:
                if os.path.exists(f):
                    os.unlink(f)

    return ok, fail


def main():
    parser = argparse.ArgumentParser(
        description="Remove watermark/signature from scanned math documents"
    )
    parser.add_argument("--input", type=str, help="Single input image file")
    parser.add_argument("--output", type=str, help="Single output image file")
    parser.add_argument("--input_dir", type=str, help="Input directory for batch processing")
    parser.add_argument("--output_dir", type=str, help="Output directory for batch processing")
    parser.add_argument("--gcs_input", type=str, help="GCS input URI (gs://bucket/prefix/)")
    parser.add_argument("--gcs_output", type=str, help="GCS output URI (gs://bucket/prefix/)")
    parser.add_argument(
        "--threshold", type=int, default=160,
        help="Intensity threshold (0-255). Lower = more aggressive watermark removal. Default: 160"
    )
    parser.add_argument(
        "--morph_kernel", type=int, default=2,
        help="Morphological kernel size for cleanup. Default: 2"
    )
    args = parser.parse_args()

    if args.input and args.output:
        success = process_file(args.input, args.output, args.threshold, args.morph_kernel)
        sys.exit(0 if success else 1)

    elif args.input_dir and args.output_dir:
        ok, fail = process_directory(args.input_dir, args.output_dir, args.threshold, args.morph_kernel)
        print(f"\nDone. Success: {ok} | Failed: {fail}")
        sys.exit(0 if fail == 0 else 1)

    elif args.gcs_input and args.gcs_output:
        ok, fail = process_gcs(args.gcs_input, args.gcs_output, args.threshold, args.morph_kernel)
        print(f"\nDone. Success: {ok} | Failed: {fail}")
        sys.exit(0 if fail == 0 else 1)

    else:
        parser.error(
            "Provide either --input/--output, --input_dir/--output_dir, "
            "or --gcs_input/--gcs_output"
        )


if __name__ == "__main__":
    main()
