#!/bin/bash

# A script to resize and compress images to be under 1MB

# Set the maximum dimension (height or width)
MAX_DIMENSION=1600

# Set the maximum file size in bytes (1MB = 1000000 bytes)
MAX_SIZE=1000000

# Define the input directory
INPUT_DIR="."

# Create the output directory if it doesn't exist
OUTPUT_DIR="$INPUT_DIR/optimized"
mkdir -p "$OUTPUT_DIR"

echo "Optimizing images in $INPUT_DIR..."

# Find all image files and process them
find "$INPUT_DIR" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.heic" \) | while read -r img; do
    
    filename=$(basename -- "$img")
    output_path="$OUTPUT_DIR/$filename"
    
    echo "Processing $filename..."
    
    # Use sips to resize the image to a maximum dimension, preserving aspect ratio
    sips -Z "$MAX_DIMENSION" "$img" --out "$output_path"
    
    # Check the file size and adjust quality if necessary
    file_size=$(stat -f "%z" "$output_path")
    
    # Repeatedly decrease the quality until the image is under 1MB
    quality=100
    while [ "$file_size" -gt "$MAX_SIZE" ] && [ "$quality" -gt 10 ]; do
        echo "  > File size is $file_size bytes, reducing quality..."
        quality=$((quality - 5))
        sips -s formatOptions "$quality" "$output_path" --out "$output_path"
        file_size=$(stat -f "%z" "$output_path")
    done
    
    echo "  > Optimized file saved to $output_path with quality $quality. Final size: $file_size bytes."
done

echo "Optimization complete."

