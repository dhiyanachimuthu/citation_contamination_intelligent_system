"""
Helper script to download the Retraction Watch dataset.

Usage:
    python download_retraction_watch.py [output_path]

The Retraction Watch database CSV can be downloaded from:
  https://api.retractionwatch.com/api/retractions?format=csv

Note: The API may require registration. If it fails, you can manually
download the CSV from https://retractionwatch.com/retraction-watch-database-user-guide/
and place it at: data/retraction_watch.csv
"""

import sys
import os
import requests

DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "data", "retraction_watch.csv")

URL = "https://api.retractionwatch.com/api/retractions?format=csv"

def download(output_path: str = DEFAULT_OUTPUT):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    print(f"Downloading Retraction Watch dataset from:\n  {URL}")
    print(f"Saving to: {output_path}")

    try:
        with requests.get(URL, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            total = 0
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
                    total += len(chunk)
                    print(f"  Downloaded {total // 1024:,} KB...", end="\r")
        print(f"\nDone. Saved {total // 1024:,} KB to {output_path}")
    except Exception as e:
        print(f"Download failed: {e}")
        print("\nAlternative: Download manually from:")
        print("  https://retractionwatch.com/retraction-watch-database-user-guide/")
        print(f"And place the CSV at: {output_path}")
        sys.exit(1)

if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT
    download(output)
