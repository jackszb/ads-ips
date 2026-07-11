#!/usr/bin/env python3
"""
合并多个广告 IP 规则 JSON 文件为一个统一的 reject-ip.json

数据源列表在 scripts/sources.txt 中维护，每行一个 URL。
以后如需新增数据源，只需在 sources.txt 中追加一行 URL，
本脚本无需任何修改即可自动识别并合并。

每个数据源 JSON 需符合 sing-box rule-set 格式，形如：
{
  "version": 3,
  "rules": [
    { "ip_cidr": ["1.2.3.0/24", "..."] }
  ]
}

输出文件固定为 version = 3，且对所有 ip_cidr 去重、排序后
合并到单个 rules 条目中。
"""

import json
import sys
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCES_FILE = SCRIPT_DIR / "sources.txt"
OUTPUT_FILE = SCRIPT_DIR.parent / "rules" / "reject-ip.json"
OUTPUT_VERSION = 3


def load_sources() -> list[str]:
    if not SOURCES_FILE.exists():
        print(f"错误: 未找到数据源文件 {SOURCES_FILE}", file=sys.stderr)
        sys.exit(1)

    urls = []
    for raw_line in SOURCES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)

    if not urls:
        print("错误: 数据源文件中没有有效的 URL", file=sys.stderr)
        sys.exit(1)

    return urls


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw)


def extract_ip_cidr(doc: dict) -> list[str]:
    """从 sing-box rule-set 格式的 JSON 中提取所有 ip_cidr 条目"""
    cidrs: list[str] = []
    for rule in doc.get("rules", []):
        cidrs.extend(rule.get("ip_cidr", []))
    return cidrs


def main() -> None:
    urls = load_sources()

    all_cidrs: list[str] = []
    seen: set[str] = set()
    failed_sources = 0

    for url in urls:
        print(f"下载: {url}")
        try:
            doc = fetch_json(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  警告: 下载或解析失败，已跳过 -> {exc}", file=sys.stderr)
            failed_sources += 1
            continue

        cidrs = extract_ip_cidr(doc)
        added = 0
        for cidr in cidrs:
            if cidr not in seen:
                seen.add(cidr)
                all_cidrs.append(cidr)
                added += 1
        print(f"  提取到 {len(cidrs)} 条，新增 {added} 条（去重后）")

    if not all_cidrs:
        print("错误: 未从任何数据源获取到 ip_cidr 规则，终止", file=sys.stderr)
        sys.exit(1)

    all_cidrs.sort()

    merged = {
        "version": OUTPUT_VERSION,
        "rules": [
            {
                "ip_cidr": all_cidrs,
            }
        ],
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"\n完成: 已生成 {OUTPUT_FILE}\n"
        f"  数据源总数: {len(urls)}（失败 {failed_sources} 个）\n"
        f"  合并后规则条数: {len(all_cidrs)}"
    )

    if failed_sources:
        # 有源失败但仍有数据产出时，不让工作流失败，只提示
        print("提示: 部分数据源下载失败，请检查上方警告信息。", file=sys.stderr)


if __name__ == "__main__":
    main()
