import html
import json
import os
import re
import smtplib
import tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import feedparser
import yt_dlp


# --------------------------------------------------
# 채널 정보 불러오기
# --------------------------------------------------
def load_channels():
    with open("channels.json", "r", encoding="utf-8") as file:
        return json.load(file)


# --------------------------------------------------
# RSS에서 최신 영상 가져오기
# --------------------------------------------------
def get_latest_video_from_rss(channel_id):
    rss_url = (
        f"https://www.youtube.com/feeds/videos.xml"
        f"?channel_id={channel_id}"
    )

    feed = feedparser.parse(rss_url)

    if not feed.entries:
        return None

    entry = feed.entries[0]

    video_id = getattr(entry, "yt_videoid", None)

    if not video_id:
        video_id = entry.get("yt_videoid")

    if not video_id:
        return None

    return {
        "title": entry.title,
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


# --------------------------------------------------
# RSS 실패 시 YouTube Shorts 탭에서 최신 영상 가져오기
# --------------------------------------------------
def get_latest_video_from_shorts(channel_id):
    shorts_url = (
        f"https://www.youtube.com/channel/{channel_id}/shorts"
    )

    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": 5,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                shorts_url,
                download=False,
            )

        entries = info.get("entries") or []

        if not entries:
            return None

        video = entries[0]

        video_id = video.get("id")

        if not video_id:
            return None

        return {
            "title": video.get("title") or "Untitled video",
            "video_id": video_id,
            "url": f"https://www.youtube.com/shorts/{video_id}",
        }

    except Exception as error:
        print(
            f"Shorts search failed for {channel_id}: "
            f"{type(error).__name__}: {error}"
        )
        return None


# --------------------------------------------------
# 최신 영상 찾기
# RSS 우선, 실패하면 Shorts 탭 확인
# --------------------------------------------------
def get_latest_video(channel_id):
    video = get_latest_video_from_rss(channel_id)

    if video:
        return video

    return get_latest_video_from_shorts(channel_id)


# --------------------------------------------------
# VTT 자막 파일을 일반 텍스트로 정리
# --------------------------------------------------
def clean_vtt_text(vtt_text):
    cleaned_lines = []
    previous_line = ""

    for raw_line in vtt_text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line == "WEBVTT":
            continue

        if line.startswith(
            (
                "Kind:",
                "Language:",
                "NOTE",
                "Style:",
                "Region:",
            )
        ):
            continue

        if "-->" in line:
            continue

        if line.isdigit():
            continue

        # HTML/VTT 태그 제거
        line = re.sub(r"<[^>]+>", "", line)

        # 자막 내부 타임스탬프 제거
        line = re.sub(
            r"\d{1,2}:\d{2}:\d{2}\.\d{3}",
            "",
            line,
        )
        line = re.sub(
            r"\d{1,2}:\d{2}\.\d{3}",
            "",
            line,
        )

        # HTML 특수문자 복원
        line = html.unescape(line)

        # 공백 정리
        line = re.sub(r"\s+", " ", line).strip()

        if not line:
            continue

        # 바로 앞 문장과 완전히 같으면 제외
        if line == previous_line:
            continue

        # 자동 자막이 앞 문장을 확장해서 반복하는 경우 처리
        if previous_line and line.startswith(previous_line):
            if cleaned_lines:
                cleaned_lines[-1] = line
            previous_line = line
            continue

        cleaned_lines.append(line)
        previous_line = line

    return "\n".join(cleaned_lines)


# --------------------------------------------------
# yt-dlp로 영어 자막 가져오기
# --------------------------------------------------
def get_english_transcript(video_id):
    video_url = (
        f"https://www.youtube.com/watch?v={video_id}"
    )

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_template = str(
                Path(temp_dir) / "%(id)s.%(ext)s"
            )

            options = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": [
                    "en",
                    "en-US",
                    "en-GB",
                    "en-orig",
                ],
                "subtitlesformat": "vtt",
                "outtmpl": output_template,
                "quiet": False,
                "no_warnings": False,
                "ignoreerrors": False,
            }

            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([video_url])

            subtitle_files = list(
                Path(temp_dir).glob(
                    f"{video_id}*.vtt"
                )
            )

            if not subtitle_files:
                print(
                    f"No English subtitle file found: "
                    f"{video_id}"
                )
                return None

            # 영어 원문 자막을 우선 선택
            preferred_file = None

            preferred_patterns = [
                ".en-orig.vtt",
                ".en.vtt",
                ".en-US.vtt",
                ".en-GB.vtt",
            ]

            for pattern in preferred_patterns:
                for subtitle_file in subtitle_files:
                    if subtitle_file.name.endswith(pattern):
                        preferred_file = subtitle_file
                        break

                if preferred_file:
                    break

            if not preferred_file:
                preferred_file = subtitle_files[0]

            vtt_text = preferred_file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            transcript = clean_vtt_text(vtt_text)

            if not transcript:
                print(
                    f"Subtitle file was empty after cleaning: "
                    f"{video_id}"
                )
                return None

            print(
                f"Transcript retrieved successfully: "
                f"{video_id}"
            )

            return transcript

    except Exception as error:
        print(
            f"yt-dlp transcript unavailable for "
            f"{video_id}: "
            f"{type(error).__name__}: {error}"
        )
        return None


# --------------------------------------------------
# HTML 자막 박스 만들기
# --------------------------------------------------
def format_transcript_html(transcript):
    if not transcript:
        return """
        <p style="
            color:#777777;
            font-style:italic;
            line-height:1.6;
        ">
            English transcript unavailable.
        </p>
        """

    safe_transcript = html.escape(transcript)

    return f"""
    <div style="
        margin-top:12px;
        padding:16px;
        background:#f6f7f8;
        border-radius:8px;
        font-size:15px;
        line-height:1.8;
        white-space:pre-wrap;
        color:#222222;
    ">{safe_transcript}</div>
    """


# --------------------------------------------------
# 메일 내용 만들기
# --------------------------------------------------
def build_email_content(channels):
    html_sections = []
    text_sections = []

    for channel in channels:
        channel_name = channel["name"]
        channel_id = channel["channel_id"]

        print(f"Checking channel: {channel_name}")

        video = get_latest_video(channel_id)

        if not video:
            print(f"No video found: {channel_name}")
            continue

        print(
            f"Latest video: {channel_name} / "
            f"{video['title']}"
        )

        transcript = get_english_transcript(
            video["video_id"]
        )

        safe_channel_name = html.escape(channel_name)
        safe_title = html.escape(video["title"])
        safe_url = html.escape(video["url"])

        html_sections.append(
            f"""
            <div style="
                margin-bottom:32px;
                padding-bottom:30px;
                border-bottom:1px solid #dddddd;
            ">
                <h2 style="
                    margin:0 0 10px 0;
                    font-size:22px;
                ">
                    {safe_channel_name}
                </h2>

                <p style="
                    margin:0 0 12px 0;
                    font-size:17px;
                    font-weight:bold;
                    line-height:1.5;
                ">
                    {safe_title}
                </p>

                <p style="margin:0 0 18px 0;">
                    <a
                        href="{safe_url}"
                        style="
                            color:#1a73e8;
                            text-decoration:none;
                        "
                    >
                        Watch on YouTube
                    </a>
                </p>

                <h3 style="
                    margin:0 0 8px 0;
                    font-size:18px;
                ">
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
{channel_name}

{video["title"]}

{video["url"]}

English Transcript

{text_transcript}

----------------------------------------
"""
        )

    if not html_sections:
        raise RuntimeError(
            "보낼 영상을 찾지 못했습니다."
        )

    html_body = f"""
    <html>
        <body style="
            max-width:680px;
            margin:0 auto;
            padding:24px;
            font-family:Arial, Helvetica, sans-serif;
            color:#222222;
        ">
            <h1 style="
                margin:0 0 32px 0;
                font-size:30px;
                line-height:1.3;
            ">
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


# --------------------------------------------------
# Gmail 발송
# --------------------------------------------------
def send_email(html_body, text_body):
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_app_password = os.getenv(
        "GMAIL_APP_PASSWORD"
    )

    if not gmail_address or not gmail_app_password:
        raise RuntimeError(
            "Gmail 환경변수가 설정되지 않았습니다."
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = "Today's English Shorts"
    message["From"] = gmail_address
    message["To"] = gmail_address

    message.attach(
        MIMEText(
            text_body,
            "plain",
            "utf-8",
        )
    )

    message.attach(
        MIMEText(
            html_body,
            "html",
            "utf-8",
        )
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


# --------------------------------------------------
# 실행
# --------------------------------------------------
def main():
    channels = load_channels()

    html_body, text_body = build_email_content(
        channels
    )

    send_email(
        html_body,
        text_body,
    )

    print("Email sent successfully.")


if __name__ == "__main__":
    main()
