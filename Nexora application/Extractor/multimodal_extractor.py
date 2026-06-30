# multimodal_extractor.py
# MultimodalAssetExtractor — Phase 4A
# Isolates images, videos, and alt-text from HTML.
# Produces structured asset metadata without downloading binaries.

import logging
from typing import List, Dict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class MultimodalAssetExtractor:
    """
    Extracts image and video references from HTML.
    Does NOT download binaries — only captures metadata and URLs.
    """

    def extract(self, html: str, base_url: str = "") -> Dict:
        """
        Returns structured asset metadata.

        Returns:
            {
                "images": [
                    {
                        "src": "https://.../image.jpg",
                        "alt": "Description",
                        "width": "800",
                        "height": "600",
                        "loading": "lazy",
                        "is_hero": False,
                    }
                ],
                "videos": [
                    {
                        "src": "https://.../video.mp4",
                        "poster": "...",
                        "type": "video/mp4",
                    }
                ],
                "total_images": 5,
                "total_videos": 1,
                "has_hero_image": False,
            }
        """
        if not html:
            return self._empty_result()

        soup = BeautifulSoup(html, "lxml")

        images = self._extract_images(soup, base_url)
        videos = self._extract_videos(soup, base_url)

        # Hero image heuristic: first large image above the fold
        has_hero = False
        if images:
            first_img = images[0]
            width = int(first_img.get("width") or 0)
            height = int(first_img.get("height") or 0)
            if width >= 600 or height >= 400:
                first_img["is_hero"] = True
                has_hero = True

        return {
            "images": images,
            "videos": videos,
            "total_images": len(images),
            "total_videos": len(videos),
            "has_hero_image": has_hero,
        }

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                src = urljoin(base_url, src)

            # Also check srcset for highest resolution
            srcset = img.get("srcset", "")
            best_src = src
            if srcset:
                candidates = [
                    (urljoin(base_url, part.strip().split()[0]),
                     int(part.strip().split()[1].replace("w", "")) 
                     if len(part.strip().split()) > 1 else 0)
                    for part in srcset.split(",")
                ]
                if candidates:
                    best_src = max(candidates, key=lambda x: x[1])[0]

            images.append({
                "src": best_src,
                "alt": img.get("alt", ""),
                "width": img.get("width", ""),
                "height": img.get("height", ""),
                "loading": img.get("loading", "eager"),
                "is_hero": False,
            })
        return images

    def _extract_videos(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        videos = []

        # <video> tags
        for vid in soup.find_all("video"):
            src = vid.get("src", "")
            if not src:
                source = vid.find("source")
                src = source.get("src", "") if source else ""

            if src:
                videos.append({
                    "src": urljoin(base_url, src),
                    "poster": urljoin(base_url, vid.get("poster", "")),
                    "type": vid.get("type", ""),
                    "width": vid.get("width", ""),
                    "height": vid.get("height", ""),
                })

        # iframe embeds (YouTube, Vimeo, etc.)
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src", "")
            if any(domain in src for domain in ["youtube", "vimeo", "dailymotion"]):
                videos.append({
                    "src": src,
                    "poster": "",
                    "type": "embed",
                    "platform": "youtube" if "youtube" in src else "vimeo",
                })

        return videos

    def _empty_result(self) -> Dict:
        return {
            "images": [],
            "videos": [],
            "total_images": 0,
            "total_videos": 0,
            "has_hero_image": False,
        }