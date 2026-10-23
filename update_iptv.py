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

def channel_key(info, region):
    match = re.search(r'tvg-id="([^"]+)"', info, re.IGNORECASE)
    if match and match.group(1).strip():
        return (region, match.group(1).strip().lower())
    name = info.rsplit(",", 1)[-1].strip()
    name = re.sub(r"\\s*\\(備用\\d+\\)$", "", name)
    return (region, name.casefold())


def set_region(info, region):
    if re.search(r'group-title="[^"]*"', info):
        return re.sub(r'group-title="[^"]*"', f'group-title="{region}"', info)
    # Keep the EXTINF duration immediately after the colon.
    return re.sub(r'^(#EXTINF:[^ ,]+)', rf'\\1 group-title="{region}"', info, count=1)


def main():
    previous = parse_playlist(OUTPUT.read_text(encoding="utf-8-sig")) if OUTPUT.exists() else []
    groups = {}
    seen_urls = set()
    successful = 0
    failed_regions = set()
    max_sources = 4

    def add_entry(region, info, options, stream_url, front=False):
        if region not in SOURCES or stream_url in seen_urls:
            return
        if re.search(r'tvg-country="(?:JP|KR)"', info, re.IGNORECASE):
            return
        key = channel_key(info, region)
        group = groups.setdefault(key, [])
        if len(group) >= max_sources:
            return
        seen_urls.add(stream_url)
        entry = (set_region(info, region), options, stream_url)
        if front:
            group.insert(0, entry)
        else:
            group.append(entry)

    # Prioritize previously working Jade URL, without restoring removed regions.
    for info, options, stream_url in previous:
        region_match = re.search(r'group-title="([^"]+)"', info)
        region = region_match.group(1) if region_match else None
        if region == "香港" and re.search(r'tvg-id="Jade\\.hk(?:@[^"]*)?"', info, re.IGNORECASE):
            add_entry(region, info, options, stream_url)

    for region, url in SOURCES.items():
        print(f"正在更新：{region}")
        try:
            content = download(url)
            entries = parse_playlist(content)
            if not content.lstrip("\\ufeff").startswith("#EXTM3U") or not entries:
                raise ValueError("來源不是有效或非空的 M3U")
            successful += 1
            for info, options, stream_url in entries:
                add_entry(region, info, options, stream_url)
            print(f"完成：{region}")
        except Exception as error:
            failed_regions.add(region)
            print(f"更新失敗：{region}，原因：{error}")

    if successful == 0:
        raise RuntimeError("所有直播源下載失敗，保留舊播放列表")

    # Keep old channels from a region only when that region fails to update.
    for info, options, stream_url in previous:
        region_match = re.search(r'group-title="([^"]+)"', info)
        region = region_match.group(1) if region_match else None
        if region in failed_regions:
            add_entry(region, info, options, stream_url)

    playlist = ["#EXTM3U"]
    for entries in groups.values():
        for index, (info, options, stream_url) in enumerate(entries):
            if index:
                info = re.sub(r"\\s*\\(備用\\d+\\)$", "", info)
                info += f" (備用{index})"
            playlist.extend([info, *options, stream_url])

    if len(playlist) == 1:
        raise RuntimeError("沒有取得任何頻道，保留舊播放列表")

    temporary = OUTPUT.with_suffix(".m3u.tmp")
    temporary.write_text("\\n".join(playlist) + "\\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"更新完成！共 {sum(len(v) for v in groups.values())} 條線路")

if __name__ == "__main__":
    main()
