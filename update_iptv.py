import re
import urllib.request
from pathlib import Path

# IPTV 公開來源
SOURCES = {
    "中國大陸": "https://iptv-org.github.io/iptv/countries/cn.m3u",
    "香港": "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "澳門": "https://iptv-org.github.io/iptv/countries/mo.m3u",
    "台灣": "https://iptv-org.github.io/iptv/countries/tw.m3u",
    "美國": "https://iptv-org.github.io/iptv/countries/us.m3u",
    "英國": "https://iptv-org.github.io/iptv/countries/uk.m3u",
    "加拿大": "https://iptv-org.github.io/iptv/countries/ca.m3u",
    "澳洲": "https://iptv-org.github.io/iptv/countries/au.m3u",
}

OUTPUT = Path("IPTV.m3u")

def download(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig", errors="replace")

def parse_playlist(content):
    lines = content.splitlines()
    entries = []
    info = None
    options = []

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF:"):
            info = line
            options = []

        elif info and line.startswith("#"):
            options.append(line)

        elif info and line and not line.startswith("#"):
            entries.append((info, options.copy(), line))
            info = None
            options = []

    return entries

def main():
    playlist = ["#EXTM3U"]
    seen = set()
    total = 0
    successful = 0

    previous = parse_playlist(OUTPUT.read_text(encoding="utf-8-sig")) if OUTPUT.exists() else []
    failed_regions = set()

    for region, url in SOURCES.items():
        print(f"正在更新：{region}")

        try:
            content = download(url)
            entries = parse_playlist(content)
            if not content.lstrip("\ufeff").startswith("#EXTM3U") or not entries:
                raise ValueError("來源不是有效或非空的 M3U")
            successful += 1

            for info, options, stream_url in entries:
                # 按直播地址去重
                if stream_url in seen:
                    continue

                # 排除明確標記為日本或韓國的頻道
                if re.search(
                    r'tvg-country="(?:JP|KR)"',
                    info,
                    re.IGNORECASE
                ):
                    continue

                seen.add(stream_url)

                # 使用地區名稱作為頻道分類
                info = re.sub(
                    r'group-title="[^"]*"',
                    f'group-title="{region}"',
                    info
                )

                if 'group-title="' not in info:
                    info = info.replace(
                        "#EXTINF:",
                        f'#EXTINF: group-title="{region}" ',
                        1
                    )

                playlist.append(info)
                playlist.extend(options)
                playlist.append(stream_url)

                total += 1

            print(f"完成：{region}")

        except Exception as error:
            failed_regions.add(region)
            print(f"更新失敗：{region}，原因：{error}")

    if successful == 0:
        raise RuntimeError("所有直播源下載失敗，保留舊播放列表")

    if total == 0:
        raise RuntimeError("沒有取得任何頻道，保留舊播放列表")

    # Preserve failed regions and the user's working Jade URL, including VLC options.
    for info, options, stream_url in previous:
        group = re.search(r'group-title="([^"]*)"', info)
        is_jade = re.search(r'tvg-id="Jade\.hk(?:@[^"]*)?"', info, re.IGNORECASE)
        if (group and group.group(1) in failed_regions) or is_jade:
            if stream_url not in seen:
                seen.add(stream_url)
                playlist.extend([info, *options, stream_url])
                total += 1

    # Replace only after the complete playlist has been written successfully.
    temporary = OUTPUT.with_suffix(".m3u.tmp")
    temporary.write_text(
        "\n".join(playlist) + "\n",
        encoding="utf-8"
    )

    temporary.replace(OUTPUT)

    print(f"更新完成！共 {total} 條直播源")

if __name__ == "__main__":
    main()
