import html
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
from youtube_transcript_api import YouTubeTranscriptApi


def load_channels():
    with open("channels.json", "r", encoding="utf-8") as file:
        return json.load(file)


def get_latest_video(channel_id):
    rss_url = (
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    )
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        return None

    entry = feed.entries[0]

    return {
        "title": entry.title,
        "video_id": entry.yt_videoid,
        "url": f"https://www.youtube.com/watch?v={entry.yt_videoid}",
    }


def get_english_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi().fetch(
            video_id,
            languages=["en", "en-US", "en-GB"],
        )

        lines = []

        for snippet in transcript:
            text = snippet.text.strip()

            if text:
                lines.append(text)

        if not lines:
            return None

        return "\n".join(lines)

    except Exception as error:
        print(
            f"Transcript unavailable for {video_id}: "
            f"{type(error).__name__}: {error}"
        )
        return None


def format_transcript_html(transcript):
    if not transcript:
        return """
        <p style="color:#777777; font-style:italic;">
            English transcript unavailable.
        </p>
        """

    escaped_transcript = html.escape(transcript)

    return f"""
    <div style="
        margin-top:14px;
        padding:16px;
        background:#f6f7f8;
        border-radius:8px;
        font-size:15px;
        line-height:1.7;
        white-space:pre-wrap;
        color:#222222;
    ">{escaped_transcript}</div>
    """


def build_email_content(channels):
    html_sections = []
    text_sections = []

    for channel in channels:
        video = get_latest_video(channel["channel_id"])

        if not video:
            print(f"No video found: {channel['name']}")
            continue

        transcript = get_english_transcript(video["video_id"])

        safe_channel_name = html.escape(channel["name"])
        safe_title = html.escape(video["title"])
        safe_url = html.escape(video["url"])

        html_sections.append(
            f"""
            <div style="
                margin-bottom:28px;
                padding-bottom:28px;
                border-bottom:1px solid #dddddd;
            ">
                <h2 style="margin-bottom:8px;">
                    {safe_channel_name}
                </h2>

                <p style="
                    margin:0 0 10px 0;
                    font-size:17px;
                    font-weight:bold;
                ">
                    {safe_title}
                </p>

                <p style="margin:0 0 14px 0;">
                    <a href="{safe_url}">
                        Watch on YouTube
                    </a>
                </p>

                <h3 style="margin:18px 0 8px 0;">
                    English Transcript
                </h3>

                {format_transcript_html(transcript)}
            </div>
            """
        )

        text_transcript = (
            transcript
            if transcript
            else "English transcript unavailable."
        )

        text_sections.append(
            f"""
{channel["name"]}

{video["title"]}

{video["url"]}

English Transcript

{text_transcript}

----------------------------------------
"""
        )

    if not html_sections:
        raise RuntimeError("보낼 영상이 없습니다.")

    html_body = f"""
    <html>
        <body style="
            max-width:680px;
            margin:0 auto;
            padding:24px;
            font-family:Arial, sans-serif;
            color:#222222;
        ">
            <h1 style="margin-bottom:30px;">
                Today's English Shorts
            </h1>

            {''.join(html_sections)}
        </body>
    </html>
    """

    text_body = (
        "Today's English Shorts\n\n"
        + "\n".join(text_sections)
    )

    return html_body, text_body


def send_email(html_body, text_body):
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_app_password:
        raise RuntimeError(
            "Gmail 환경변수가 설정되지 않았습니다."
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = "Today's English Shorts"
    message["From"] = gmail_address
    message["To"] = gmail_address

    message.attach(
        MIMEText(text_body, "plain", "utf-8")
    )
    message.attach(
        MIMEText(html_body, "html", "utf-8")
    )

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
    ) as smtp:
        smtp.login(
            gmail_address,
            gmail_app_password,
        )
        smtp.send_message(message)


def main():
    channels = load_channels()
    html_body, text_body = build_email_content(channels)
    send_email(html_body, text_body)

    print("Email sent successfully.")


if __name__ == "__main__":
    main()
