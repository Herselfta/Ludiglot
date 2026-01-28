from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ludiglot.core.audio_mapper import AudioCacheIndex


@dataclass
class ConvertResult:
    converted: int
    skipped: int
    failed: int


def default_vgmstream_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    # FModelCLI 自动将 vgmstream 安装到 tools/.data 目录中
    return root / "tools" / ".data" / "vgmstream-cli.exe"


def default_wwiser_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "tools" / "wwiser.pyz"


def _filter_paths(
    paths: Iterable[Path],
    extensions: Iterable[str],
    contains: Iterable[str] | None = None,
) -> list[Path]:
    ext_set = {ext.lower() for ext in extensions}
    contains_list = [c.lower() for c in (contains or [])]
    results: list[Path] = []
    for path in paths:
        if path.suffix.lower() not in ext_set:
            continue
        lower = str(path).lower()
        if contains_list and not all(token in lower for token in contains_list):
            continue
        results.append(path)
    return results


def collect_wem_files(
    wem_root: Path,
    extensions: Iterable[str] | None = None,
    contains: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[Path]:
    if not wem_root.exists():
        raise FileNotFoundError(f"WEM 目录不存在: {wem_root}")
    ext = list(extensions or [".wem"])
    files = [p for p in wem_root.rglob("*") if p.is_file()]
    filtered = _filter_paths(files, ext, contains)
    if limit:
        filtered = filtered[: int(limit)]
    return filtered


def find_wem_by_hash(wem_root: Path, hash_value: int) -> Path | None:
    direct = wem_root / f"{hash_value}.wem"
    if direct.exists():
        return direct
    try:
        for path in wem_root.rglob(f"{hash_value}.wem"):
            if path.is_file():
                return path
    except Exception:
        return None
    return None


def find_wem_by_event_name(
    wem_root: Path,
    event_name: str | None,
    external_root: Path | None = None,
) -> Path | None:
    if not event_name:
        return None
    token = event_name.strip().lower()
    if not token:
        return None
    for prefix in ("play_", "vo_", "p_vo_", "play_vo_"):
        if token.startswith(prefix):
            token = token[len(prefix) :]
            break

    candidates: list[Path] = []
    roots = [wem_root]
    if external_root:
        roots.append(external_root)
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.wem"):
            stem = path.stem.lower()
            if token in stem:
                candidates.append(path)

    if not candidates:
        return None
    # 优先选择最短路径（更可能是直接外部源）
    candidates.sort(key=lambda p: len(str(p)))
    return candidates[0]


def find_bnk_for_event(bnk_root: Path, event_name: str | None) -> Path | None:
    if not event_name:
        return None
    
    # 极简归一化：去掉所有非字母数字且下划线的字符
    token = event_name.lower().replace(".", "_")
    if token.startswith("play_"):
        core = token[5:]
    else:
        core = token

    # 1. 精确匹配
    direct = bnk_root / f"{token}.bnk"
    if direct.exists():
        return direct
        
    # 2. 模糊匹配：寻找包含核心部分的 BNK
    # 例如 core="favor_word_linnai_favorword_150904_content"
    # 我们检查是否有 BNK 包含 "favorword_150904"
    sub_token = core
    if "_" in core:
         parts = core.split("_")
         # 尝试后半段更具体的 ID
         if len(parts) > 2:
             sub_token = "_".join(parts[-2:])
    
    for path in bnk_root.rglob("*.bnk"):
        stem = path.stem.lower()
        if token in stem or core in stem or (sub_token and sub_token in stem):
            return path
            
    # 3. 针对 鸣潮 的特殊回退：角色名直接作为 Bank 名 (例如 VO_Linnai.bnk)
    # 假设核心类似 favor_word_linnai_...
    for char_name in ["linnai", "yangyang", "chixia", "baizhi", "jiyan"]:
        if char_name in core:
            for p in bnk_root.rglob(f"*VO_{char_name}*.bnk"):
                return p
            for p in bnk_root.rglob(f"*{char_name}*.bnk"):
                return p

    return None


def convert_single_wem_to_wav(
    wem_path: Path,
    vgmstream_path: Path,
    output_dir: Path,
) -> Path:
    if not wem_path.exists():
        raise FileNotFoundError(f"WEM 不存在: {wem_path}")
    if not vgmstream_path.exists():
        raise FileNotFoundError(f"vgmstream-cli.exe 不存在: {vgmstream_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{wem_path.stem}.wav"
    cmd = [str(vgmstream_path), "-o", str(out_path), str(wem_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_path


def generate_txtp_for_bnk(
    bnk_path: Path,
    wem_root: Path,
    txtp_root: Path,
    wwiser_path: Path,
    language: str = "zh",
    log_callback: callable | None = None,
) -> list[Path]:
    if not bnk_path.exists():
        raise FileNotFoundError(f"BNK 不存在: {bnk_path}")
    if not wwiser_path.exists():
        raise FileNotFoundError(f"wwiser.pyz 不存在: {wwiser_path}")
    if not wem_root.exists():
        raise FileNotFoundError(f"WEM 目录不存在: {wem_root}")
    out_dir = txtp_root / bnk_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.rglob("*.txtp"))
    if existing:
        return existing
    cmd = [
        sys.executable,
        str(wwiser_path),
        "-g",
        "-go",
        str(out_dir),
        "-gw",
        str(wem_root),
    ]
    # 首先尝试带语言参数
    def _log(msg: str) -> None:
        if log_callback:
            log_callback(msg)
        else:
            print(msg, flush=True)

    try:
        result = subprocess.run(
            [*cmd, "-gl", language, str(bnk_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.stdout:
            _log(result.stdout.strip())
        if result.stderr:
            _log(result.stderr.strip())
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            _log(exc.stdout.strip())
        if exc.stderr:
            _log(exc.stderr.strip())
    except Exception as exc:
        _log(f"[WWISER] 调用失败: {exc}")
    txtp_files = list(out_dir.rglob("*.txtp"))
    if txtp_files:
        return txtp_files
    # 若未生成，回退不带语言过滤的生成方式
    result = subprocess.run(
        [*cmd, str(bnk_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.stdout:
        _log(result.stdout.strip())
    if result.stderr:
        _log(result.stderr.strip())
    return list(out_dir.rglob("*.txtp"))


def find_txtp_for_event(txtp_root: Path, event_name: str | None, event_hash: int | None = None) -> Path | None:
    if not event_name:
        return None
    token = event_name.lower()
    hash_str = str(event_hash) if event_hash is not None else "____"

    for path in txtp_root.rglob("*.txtp"):
        stem = path.stem.lower()
        if token in stem or hash_str in stem:
            return path
    return None


def convert_txtp_to_wav(
    txtp_path: Path,
    vgmstream_path: Path,
    output_path: Path,
) -> Path:
    if not txtp_path.exists():
        raise FileNotFoundError(f"TXTP 不存在: {txtp_path}")
    if not vgmstream_path.exists():
        raise FileNotFoundError(f"vgmstream-cli.exe 不存在: {vgmstream_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 强制后缀为 .wav 以确保 vgmstream 生成正确的容器，且 QtMultimedia 正常播放
    if output_path.suffix.lower() != ".wav":
        output_path = output_path.with_suffix(".wav")
    cmd = [str(vgmstream_path), "-o", str(output_path), str(txtp_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def convert_wem_to_wav(
    wem_files: Sequence[Path],
    vgmstream_path: Path,
    output_dir: Path,
    *,
    preserve_paths: bool = False,
    root_dir: Path | None = None,
    skip_existing: bool = True,
) -> ConvertResult:
    if not vgmstream_path.exists():
        raise FileNotFoundError(f"vgmstream-cli.exe 不存在: {vgmstream_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    converted = 0
    skipped = 0
    failed = 0
    for wem in wem_files:
        if preserve_paths:
            rel = wem.name
            if root_dir is not None:
                try:
                    rel = wem.relative_to(root_dir)
                except Exception:
                    rel = wem.name
            out_path = output_dir / rel
            out_path = out_path.with_suffix(".wav")
        else:
            out_path = output_dir / f"{wem.stem}.wav"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if skip_existing and out_path.exists():
            skipped += 1
            continue
        cmd = [str(vgmstream_path), "-o", str(out_path), str(wem)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            converted += 1
        except subprocess.CalledProcessError:
            failed += 1
    return ConvertResult(converted=converted, skipped=skipped, failed=failed)


def build_audio_index(cache_dir: Path, index_path: Path | None = None, max_mb: int = 2048) -> AudioCacheIndex:
    index = AudioCacheIndex(cache_dir, index_path=index_path, max_mb=max_mb)
    index.scan()
    return index
