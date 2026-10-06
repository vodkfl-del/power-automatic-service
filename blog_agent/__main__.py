"""명령줄 실행.

  python -m blog_agent chrome                         디버깅용 크롬 실행 (처음 1회 로그인)
  python -m blog_agent check                          사이트별 셀렉터 점검
  python -m blog_agent run --topic "주제"              전체 실행
  python -m blog_agent run --topics-file topics.txt   여러 주제 연속 실행
  python -m blog_agent run --topic "주제" --only images naver   특정 단계만
  python -m blog_agent convert article.html --title "제목"      HTML → 스마트에디터용 변환만 (브라우저 불필요)
  python -m blog_agent lint                           프롬프트 거절 위험 표현 점검
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .config import ROOT, load_config


def _setup_logging(output_dir: str) -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    logfile = Path(output_dir) / f"run_{time.strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(logfile, encoding="utf-8")],
    )


def _default_config() -> str | None:
    p = ROOT / "config.yaml"
    return str(p) if p.exists() else None


def cmd_chrome(cfg, args) -> int:
    from .browser import launch_debug_chrome
    launch_debug_chrome(cfg)
    return 0


def cmd_run(cfg, args) -> int:
    from .browser import open_context
    from .pipeline import run_topic

    topics = list(args.topic or [])
    if args.topics_file:
        lines = Path(args.topics_file).read_text(encoding="utf-8").splitlines()
        topics += [t.strip() for t in lines if t.strip() and not t.startswith("#")]
    if not topics:
        print("--topic 또는 --topics-file 을 지정하세요.")
        return 2

    failed = []
    with open_context(cfg) as context:
        for topic in topics:
            try:
                run_topic(context, cfg, topic, set(args.only) if args.only else None, force=args.force)
            except Exception as e:  # 한 주제가 실패해도 다음 주제는 계속
                logging.exception("주제 실패: %s (%s)", topic, e)
                failed.append(topic)
    if failed:
        logging.error("실패한 주제 %d개: %s  → 같은 명령으로 다시 실행하면 실패 단계부터 이어서 진행합니다.",
                      len(failed), failed)
        return 1
    return 0


def cmd_convert(cfg, args) -> int:
    from .naver_converter import convert_file
    doc = convert_file(Path(args.file), args.title, cfg["images"]["count"])
    out = Path(args.out or Path(args.file).with_name("article_naver.html"))
    out.write_text(doc.preview_html(), encoding="utf-8")
    print(f"변환 완료: {out}  (조각 {len(doc.segments)}개)")
    return 0


def cmd_lint(cfg, args) -> int:
    from .refusal import lint_prompt
    text = Path(args.file or cfg["writing"]["prompt_file"]).read_text(encoding="utf-8")
    warns = lint_prompt(text)
    for w in warns:
        print("⚠", w)
    print("문제 없음" if not warns else f"\n{len(warns)}개 항목 확인 필요")
    return 0


def cmd_check(cfg, args) -> int:
    """각 사이트를 열어 셀렉터가 실제로 잡히는지 확인한다."""
    from . import dom
    from .browser import open_context

    sels = cfg["selectors"]
    targets = {
        "gemini": (sels["gemini"]["url"], ["input", "send"]),
        "chatgpt": (sels["chatgpt"]["url"], ["input", "send"]),
        "flow": (cfg["images"]["flow_url"], ["input"]),
    }
    if cfg["naver"].get("blog_id"):
        targets["naver"] = (sels["naver"]["write_url"].format(blog_id=cfg["naver"]["blog_id"]), ["title", "body"])

    with open_context(cfg) as context:
        page = context.new_page()
        for name, (url, keys) in targets.items():
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(4)
            target = (page.frame(name="mainFrame") or page) if name == "naver" else page
            for key in keys:
                try:
                    dom.first_visible(target, sels[name][key], timeout=10)
                    print(f"  OK    {name}.{key}")
                except dom.SelectorNotFound:
                    print(f"  FAIL  {name}.{key}  → 로그인 상태 확인 또는 selectors.yaml 수정 필요")
        page.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="blog_agent", description="블로그 자동 작성/업로드 에이전트")
    ap.add_argument("--config", default=_default_config(), help="설정 파일 (기본: config.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("chrome", help="디버깅 포트가 열린 크롬 실행")
    sub.add_parser("check", help="셀렉터 점검")

    r = sub.add_parser("run", help="전체 실행")
    r.add_argument("--topic", action="append", help="주제 (여러 번 지정 가능)")
    r.add_argument("--topics-file", help="한 줄에 주제 하나씩 적은 파일")
    r.add_argument("--only", nargs="+", choices=["write", "images", "convert", "naver"], help="특정 단계만 실행")
    r.add_argument("--force", action="store_true", help="완료된 단계도 다시 실행")

    c = sub.add_parser("convert", help="HTML → 스마트에디터용 변환")
    c.add_argument("file")
    c.add_argument("--title", default="")
    c.add_argument("--out")

    l = sub.add_parser("lint", help="프롬프트 거절 위험 점검")
    l.add_argument("file", nargs="?")

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    _setup_logging(cfg["output_dir"])
    return {"chrome": cmd_chrome, "check": cmd_check, "run": cmd_run,
            "convert": cmd_convert, "lint": cmd_lint}[args.cmd](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
