"""Exercise the local API; real Telegram publication requires --publish explicitly."""

import argparse
from pathlib import Path

import httpx

from hattrick_backend.core.config import get_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8020")
    parser.add_argument("--publish", action="store_true", help="Send a real Telegram message")
    args = parser.parse_args()
    settings = get_settings()
    with httpx.Client(
        base_url=args.base_url,
        timeout=180,
        headers={"X-API-Key": settings.api_key.get_secret_value()},
    ) as client:

        def call(method, url, **kwargs):
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

        print("Topics:", [t["id"] for t in call("GET", "/api/v1/topics")["items"]])
        context = call("GET", "/api/v1/topics/weather/context")
        print("Retrieved chunks:", len(context["items"]))
        post = call(
            "POST",
            "/api/v1/generations",
            json={"topic_id": "weather", "target_platforms": ["telegram"]},
        )
        url = f"/api/v1/posts/{post['id']}"
        post = call("GET", url)
        # Saving an edit demonstrates revision creation without changing factual content.
        post = call(
            "PATCH", url, json={"expected_revision": post["revision"], "content": post["content"]}
        )
        for action in ("submit-review", "approve"):
            post = call(
                "POST",
                f"{url}/{action}",
                json={"expected_revision": post["revision"], "note": "Local demo review"},
            )
        asset = call("POST", f"{url}/render", json={})
        image = client.get(asset["download_url"])
        image.raise_for_status()
        Path("data").mkdir(exist_ok=True)
        Path("data/demo-card.png").write_bytes(image.content)
        print("Post:", post["id"], post["state"], "Card: data/demo-card.png")
        if args.publish:
            print(
                call(
                    "POST",
                    f"{url}/publish",
                    json={"platforms": ["telegram"], "idempotency_key": f"demo-{post['id']}"},
                )
            )
        print("Publication history:", call("GET", f"{url}/publications"))


if __name__ == "__main__":
    main()
