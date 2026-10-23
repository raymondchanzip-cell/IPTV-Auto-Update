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

HK_EXTRA_SOURCE = "https://raw.githubusercontent.com/ineed2underfit/hk-iptv/main/hk_live.m3u"

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
    """Group different qualities and HK aliases under one channel."""
    match = re.search(r'tvg-id="([^"]+)"', info, re.IGNORECASE)
    ident = match.group(1).strip().lower().split("@", 1)[0] if match else ""
    name = info.rsplit(",", 1)[-1].strip().casefold()
    name = re.sub(r"\s*\(備用\d+\)$", "", name)
    compact = re.sub(r"[\s_-]+", "", name)
    if region == "香港":
        if ident == "jade.hk" or compact in {"翡翠台", "jade", "翡翠台81", "tvb翡翠台", "tvb翡翠台1080p"}:
            return (region, "jade.hk")
        if ident == "viutv.hk" or compact in {"viutv", "viutv99", "viutv99台", "viutv99臺"}:
            return (region, "viutv.hk")
        if ident == "pearl.hk" or compact in {"明珠台", "pearl", "tvb明珠台"}:
            return (region, "pearl.hk")
    if ident:
        return (region, ident)
    return (region, compact)


def backup_info(info, index):
    """Suffix the visible channel name, not the stream URL or EXTINF metadata."""
    head, sep, name = info.partition(",")
    if not sep:
        return info
    name = re.sub(r"\s*\(備用\d+\)$", "", name)
    if index:
        name += f" (備用{index})"
    return head + sep + name


def set_region(info, region):
    if re.search(r'group-title="[^"]*"', info):
        return re.sub(r'group-title="[^"]*"', f'group-title="{region}"', info)
    # Keep the EXTINF duration immediately after the colon.
    return re.sub(r'^(#EXTINF:[^ ,]+)', rf'\1 group-title="{region}"', info, count=1)


NAME_MAP = {
    "Beijing Satellite TV": "北京衛視",
    "Anhui TV": "安徽衛視",
    "Hunan TV": "湖南衛視",
    "Jiangsu TV": "江蘇衛視",
    "Zhejiang TV": "浙江衛視",
    "Taiwan Television": "台視",
    "Formosa Television": "民視",
    "China Television": "中視",
    "Chinese Television System": "華視",
    "Public Television Service": "公視",
}


def localize_name(info, region):
    if region not in ("中國大陸", "台灣"):
        return info
    head, sep, name = info.partition(",")
    if not sep:
        return info
    for english, chinese in NAME_MAP.items():
        if name == english or name.startswith(english + " ("):
            return head + sep + chinese + name[len(english):]
    return info


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
        entry = (localize_name(set_region(info, region), region), options, stream_url)
        if front:
            group.insert(0, entry)
        else:
            group.append(entry)

    # Prioritize previously working Jade URL, without restoring removed regions.
    for info, options, stream_url in previous:
        region_match = re.search(r'group-title="([^"]+)"', info)
        region = region_match.group(1) if region_match else None
        if region == "香港" and re.search(r'tvg-id="Jade\.hk(?:@[^"]*)?"', info, re.IGNORECASE):
            add_entry(region, info, options, stream_url)

    for region, url in SOURCES.items():
        print(f"正在更新：{region}")
        try:
            content = download(url)
            entries = parse_playlist(content)
            if not content.lstrip("\ufeff").startswith("#EXTM3U") or not entries:
                raise ValueError("來源不是有效或非空的 M3U")
            successful += 1
            for info, options, stream_url in entries:
                add_entry(region, info, options, stream_url)
            print(f"完成：{region}")
        except Exception as error:
            failed_regions.add(region)
            print(f"更新失敗：{region}，原因：{error}")

    # Merge the additional Hong Kong playlist into the same IPTV.m3u output.
    try:
        print("正在同步香港補充播放列表")
        extra_content = download(HK_EXTRA_SOURCE)
        extra_entries = parse_playlist(extra_content)
        if not extra_content.lstrip("\ufeff").startswith("#EXTM3U") or not extra_entries:
            raise ValueError("香港補充來源無有效頻道")
        for info, options, stream_url in extra_entries:
            add_entry("香港", info, options, stream_url)
        print(f"香港補充來源收到 {len(extra_entries)} 條線路")
    except Exception as error:
        print(f"香港補充來源更新失敗，原有頻道不受影響：{error}")

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
                info = backup_info(info, index)
            playlist.extend([info, *options, stream_url])

    if len(playlist) == 1:
        raise RuntimeError("沒有取得任何頻道，保留舊播放列表")

    temporary = OUTPUT.with_suffix(".m3u.tmp")
    temporary.write_text("\n".join(playlist) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"更新完成！共 {sum(len(v) for v in groups.values())} 條線路")

if __name__ == "__main__":
    main()
