import json
import os
import smtplib
from email.message import EmailMessage
from html import escape

import feedparser


def load_channels():
    with open("channels.json", "r", encoding="utf-8") as file:
        return json.load(file)


def get_latest_video(channel):
    rss_url = (
        "https://www.youtube.com/feeds/videos.xml"
        f"?channel_id={channel['channel_id']}"
    )

    feed = feedparser.parse(rss_url)

    if not feed.entries:
        raise RuntimeError(f"{channel['name']} 채널의 영상을 찾지 못했습니다.")

    entry = feed.entries[0]

    return {
        "channel": channel["name"],
        "title": entry.title,
        "link": entry.link,
        "published": entry.get("published", ""),
    }


def build_email(videos):
    text_lines = ["Today's English Shorts", ""]

    html_items = []

    for index, video in enumerate(videos, start=1):
        text_lines.extend(
            [
                f"{index}. {video['channel']}",
                f"제목: {video['title']}",
                f"링크: {video['link']}",
                "",
            ]
        )

        html_items.append(
            f"""
            <div style="margin-bottom:24px;">
                <h3>{index}. {escape(video['channel'])}</h3>
                <p><strong>{escape(video['title'])}</strong></p>
                <p>
                    <a href="{escape(video['link'])}">
                        YouTube에서 보기
                    </a>
                </p>
            </div>
            """
        )

    text_body = "\n".join(text_lines)

    html_body = f"""
    <html>
        <body style="font-family:Arial,sans-serif;line-height:1.6;">
            <h2>Today's English Shorts</h2>
            {''.join(html_items)}
        </body>
    </html>
    """

    return text_body, html_body


def send_email(text_body, html_body):
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_password:
        raise RuntimeError("Gmail 환경변수가 설정되지 않았습니다.")

    message = EmailMessage()
    message["Subject"] = "Today's English Shorts"
    message["From"] = gmail_address
    message["To"] = gmail_address
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_address, gmail_password)
        smtp.send_message(message)


def main():
    channels = load_channels()
    videos = [get_latest_video(channel) for channel in channels]
    text_body, html_body = build_email(videos)
    send_email(text_body, html_body)

    print("메일 발송 완료")


if __name__ == "__main__":
    main()
