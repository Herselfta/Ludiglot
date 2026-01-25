from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ludiglot.core.audio_mapper import AudioCacheIndex
from ludiglot.core.config import load_config


DEFAULT_PAK_DIR = Path(r"E:\Wuthering Waves\Wuthering Waves Game\Client\Content\Paks")


@dataclass
class RepakConfig:
    repak_path: Path
    aes_key: str


def _run_repak(
    config: RepakConfig,
    args: Sequence[str],
    *,
    stdout=None,
    text: bool = False,
) -> subprocess.CompletedProcess:
    cmd = [str(config.repak_path)]
    if config.aes_key:
        cmd += ["-a", config.aes_key]
    cmd += list(args)
    try:
        return subprocess.run(
            cmd,
            check=True,
            stdout=stdout,
            stderr=subprocess.PIPE,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, (bytes, bytearray)) else str(exc.stderr)
        raise RuntimeError(f"repak 失败: {' '.join(cmd)}\n{detail}") from exc


def _list_paks(pak_dir: Path) -> list[Path]:
    return sorted(pak_dir.glob("*.pak"), key=lambda p: p.stat().st_size, reverse=True)


def _parse_list_output(output: str) -> list[str]:
    items: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(line)
    return items


def _filter_paths(
    paths: Iterable[str],
    extensions: Iterable[str],
    contains: Iterable[str] | None = None,
) -> list[str]:
    ext_set = {ext.lower() for ext in extensions}
    contains_list = [c.lower() for c in contains or []]
    results: list[str] = []
    for path in paths:
        candidate = path.strip()
        lower = candidate.lower()
        if ext_set and not any(lower.endswith(ext) for ext in ext_set):
            continue
        if contains_list and not all(token in lower for token in contains_list):
            continue
        results.append(candidate)
    return results


def _extract_files(
    config: RepakConfig,
    pak_path: Path,
    file_paths: Sequence[str],
    output_dir: Path,
    *,
    flatten: bool = True,
    skip_existing: bool = True,
) -> list[Path]:
    extracted: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for entry in file_paths:
        posix = PurePosixPath(entry)
        if flatten:
            out_path = output_dir / posix.name
        else:
            out_path = output_dir / Path(*posix.parts)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if skip_existing and out_path.exists():
            extracted.append(out_path)
            continue
        with out_path.open("wb") as fout:
            _run_repak(config, ["get", str(pak_path), entry], stdout=fout, text=False)
        extracted.append(out_path)
    return extracted


def _convert_wem_to_ogg(
    wem_files: Sequence[Path],
    vgmstream_path: Path,
    output_dir: Path,
    *,
    skip_existing: bool = True,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    for wem in wem_files:
        out_path = output_dir / f"{wem.stem}.ogg"
        if skip_existing and out_path.exists():
            results.append(out_path)
            continue
        cmd = [str(vgmstream_path), "-o", str(out_path), str(wem)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, (bytes, bytearray)) else str(exc.stderr)
            raise RuntimeError(f"vgmstream 失败: {' '.join(cmd)}\n{detail}") from exc
        results.append(out_path)
    return results


def cmd_scan(args: argparse.Namespace) -> None:
    pak_dir = Path(args.pak_dir)
    if not pak_dir.exists():
        raise FileNotFoundError(f"PAK 目录不存在: {pak_dir}")
    paks = _list_paks(pak_dir)
    if args.top:
        paks = paks[: args.top]
    for pak in paks:
        size_gb = pak.stat().st_size / (1024 ** 3)
        print(f"{pak.name}\t{size_gb:.2f} GB")


def cmd_probe(args: argparse.Namespace) -> None:
    pak_dir = Path(args.pak_dir)
    if not pak_dir.exists():
        raise FileNotFoundError(f"PAK 目录不存在: {pak_dir}")
    repak_path = Path(args.repak)
    config = RepakConfig(repak_path=repak_path, aes_key=args.aes_key)
    paks = _list_paks(pak_dir)
    if args.limit_paks:
        paks = paks[: args.limit_paks]
    results = []
    for pak in paks:
        try:
            output = _run_repak(config, ["list", str(pak)], text=True).stdout
            paths = _parse_list_output(output)
            filtered = _filter_paths(paths, args.ext, args.contains)
            results.append((pak, len(filtered)))
            print(f"{pak.name}\t{len(filtered)}")
        except Exception as exc:
            print(f"{pak.name}\tERROR: {exc}")
    if args.top:
        print("\nTop:")
        for pak, count in sorted(results, key=lambda item: item[1], reverse=True)[: args.top]:
            print(f"{pak.name}\t{count}")


def cmd_extract(args: argparse.Namespace) -> None:
    pak_path = Path(args.pak)
    if not pak_path.exists():
        raise FileNotFoundError(f"PAK 不存在: {pak_path}")
    repak_path = Path(args.repak)
    vgmstream_path = Path(args.vgmstream)
    if not repak_path.exists():
        raise FileNotFoundError(f"repak.exe 不存在: {repak_path}")
    if not vgmstream_path.exists() and not args.no_convert:
        raise FileNotFoundError(f"vgmstream-cli.exe 不存在: {vgmstream_path}")
    temp_dir = Path(args.temp_dir)
    cache_dir = Path(args.cache_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    config = RepakConfig(repak_path=repak_path, aes_key=args.aes_key)

    output = _run_repak(config, ["list", str(pak_path)], text=True).stdout
    paths = _parse_list_output(output)
    filtered = _filter_paths(paths, args.ext, args.contains)
    if args.limit_files:
        filtered = filtered[: args.limit_files]
    print(f"匹配文件: {len(filtered)}")
    if args.list_only:
        for item in filtered:
            print(item)
        return

    extracted = _extract_files(
        config,
        pak_path,
        filtered,
        temp_dir,
        flatten=not args.preserve_paths,
        skip_existing=not args.force,
    )
    print(f"已解包: {len(extracted)}")
    if args.no_convert:
        return

    oggs = _convert_wem_to_ogg(
        extracted,
        vgmstream_path,
        cache_dir,
        skip_existing=not args.force,
    )
    print(f"已转码: {len(oggs)}")
    index = AudioCacheIndex(cache_dir)
    index.scan()
    print(f"缓存索引条目: {len(index.entries)}")


def _default_cache_dir(config_path: Path | None) -> Path | None:
    if config_path is None or not config_path.exists():
        return None
    try:
        cfg = load_config(config_path)
    except Exception:
        return None
    return cfg.audio_cache_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="extract_assets")
    parser.add_argument("--config", help="可选：读取配置中的 audio_cache_path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="列出 PAK 文件及体积")
    scan.add_argument("--pak-dir", default=str(DEFAULT_PAK_DIR))
    scan.add_argument("--top", type=int, help="仅显示前 N 个")
    scan.set_defaults(func=cmd_scan)

    probe = sub.add_parser("probe", help="统计每个 PAK 中的目标资源数量")
    probe.add_argument("--pak-dir", default=str(DEFAULT_PAK_DIR))
    probe.add_argument("--repak", default=str(ROOT / "tools" / "repak.exe"))
    probe.add_argument("--aes-key", required=True)
    probe.add_argument("--ext", nargs="+", default=[".wem"], help="过滤扩展名")
    probe.add_argument("--contains", nargs="*", default=None, help="路径包含关键词")
    probe.add_argument("--limit-paks", type=int, help="仅扫描前 N 个")
    probe.add_argument("--top", type=int, help="输出 Top N")
    probe.set_defaults(func=cmd_probe)

    extract = sub.add_parser("extract", help="解包并转码 WEM 到音频缓存")
    extract.add_argument("--pak", required=True, help="目标 .pak 文件")
    extract.add_argument("--repak", default=str(ROOT / "tools" / "repak.exe"))
    extract.add_argument("--vgmstream", default=str(ROOT / "tools" / "vgmstream" / "vgmstream-cli.exe"))
    extract.add_argument("--aes-key", required=True)
    extract.add_argument("--temp-dir", default=str(ROOT / "cache" / "wem_extract"))
    extract.add_argument("--cache-dir", help="输出音频缓存目录")
    extract.add_argument("--ext", nargs="+", default=[".wem"], help="过滤扩展名")
    extract.add_argument("--contains", nargs="*", default=None, help="路径包含关键词")
    extract.add_argument("--limit-files", type=int, help="仅处理前 N 个文件")
    extract.add_argument("--list-only", action="store_true", help="仅列出匹配文件")
    extract.add_argument("--no-convert", action="store_true", help="仅解包，不转码")
    extract.add_argument("--preserve-paths", action="store_true", help="保留原路径")
    extract.add_argument("--force", action="store_true", help="覆盖已有文件")
    extract.set_defaults(func=cmd_extract)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config_path = Path(args.config) if getattr(args, "config", None) else None
    if getattr(args, "cmd", None) == "extract":
        if args.cache_dir is None:
            default_cache = _default_cache_dir(config_path)
            if default_cache is not None:
                args.cache_dir = str(default_cache)
        if args.cache_dir is None:
            raise ValueError("缺少 --cache-dir，或提供 --config 以读取 audio_cache_path")
    args.func(args)


if __name__ == "__main__":
    main()
