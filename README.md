# 블로그 자동 업로드 에이전트

API 없이 브라우저 자동화로 동작합니다.
**Gemini/ChatGPT 글 작성 → Flow/Gemini/ChatGPT 이미지 6장 → 네이버 스마트에디터 입력 → 주제별 폴더 정리**를 한 번에 처리합니다.

```
주제 ─▶ [1] 글 작성 ─▶ [2] 이미지 6장 ─▶ [3] 스마트에디터 변환·입력 ─▶ [4] output/주제/ 폴더
          Gemini            Flow                네이버 블로그                 article.html
          └실패→ChatGPT     └실패→Gemini→GPT     (기본: 임시저장)                01.png ~ 06.png
```

## 기존 오류의 원인과 이 에이전트의 대응

| 증상 | 흔한 원인 | 대응 |
|---|---|---|
| "저는 이 행동은 할 수 없어요"로 멈춤 | ① 프롬프트 안의 **행동 지시**(검색해서, 사이트 들어가서, 이미지 만들어서 등)<br>② 이전 대화의 거절 맥락이 남아 있음<br>③ 사이트 일시 오류 | `lint`로 위험 표현을 미리 경고 · 응답마다 거절 문구 감지 · **새 대화**에서 재시도 · 2회차부터 "정보성 글일 뿐 외부 행동 불필요" 안내문 추가 · 그래도 안 되면 **다른 사이트로 전환** |
| 프롬프트가 반만 전송됨 | `keyboard.type()`이 줄바꿈마다 Enter를 눌러 중간 전송 | `insert_text`로 한 번에 입력 (Enter 이벤트 없음) |
| 글이 중간에 잘림 | 스트리밍 도중 읽음 / 응답 길이 제한 | "중지 버튼 사라짐 + 텍스트 5초간 변화 없음"을 모두 확인 · `[END]` 표시가 없으면 **이어서 작성** 요청 후 합침 |
| 로그인 막힘, "안전하지 않은 브라우저" | Playwright가 띄운 자동화 브라우저를 구글이 차단 | **실제 크롬에 CDP로 접속**하는 방식 (사람이 로그인한 세션 그대로 사용) |
| UI 변경으로 갑자기 멈춤 | 사이트 개편으로 셀렉터 변경 | 셀렉터를 `selectors.yaml`로 분리 · `check` 명령으로 깨진 항목 확인 · 실패 시 `_debug/`에 스크린샷 저장 |
| 중간에 멈추면 처음부터 다시 | 진행 상태 미저장 | `state.json`에 단계별 기록 → 재실행 시 **실패 단계부터 이어서** (이미지도 없는 번호만 생성) |

## 설치

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml      # blog_id 등 수정
```

(Windows: `copy config.example.yaml config.yaml`)

## 처음 1회: 로그인

```bash
python -m blog_agent chrome
```
자동화 전용 프로필로 크롬이 열립니다. 열린 탭에서 **Gemini, ChatGPT, Flow, 네이버**에 로그인해 두세요.
로그인 정보는 `chrome-profile/`에 남기 때문에 다음부터는 다시 할 필요가 없습니다.
(이미 켜져 있는 일반 크롬과 별개의 창이므로, 실행 전에 기존 크롬을 닫을 필요는 없습니다.)

## 사용

```bash
python -m blog_agent lint                                   # 프롬프트 거절 위험 표현 점검
python -m blog_agent check                                  # 사이트별 입력칸/버튼 인식 점검
python -m blog_agent run --topic "겨울철 실내 습도 관리 방법"   # 전체 실행
python -m blog_agent run --topics-file topics.txt           # 여러 주제 연속 실행
python -m blog_agent run --topic "주제" --only images naver  # 특정 단계만
python -m blog_agent run --topic "주제" --force              # 완료 단계도 다시
python -m blog_agent convert some.html --title "제목"        # HTML → 스마트에디터용 변환만
```

## 결과 폴더

```
output/겨울철 실내 습도 관리 방법/
├─ article.html          AI가 쓴 원본 HTML
├─ article_naver.html    스마트에디터용 변환본 (브라우저로 열면 이미지 포함 미리보기)
├─ article.txt           제목·태그·본문 텍스트
├─ article.json          제목/본문/태그/이미지 프롬프트
├─ image_prompts.txt
├─ 01.png ~ 06.png       번호가 붙은 이미지
├─ raw_reply.txt         AI 원본 응답
├─ state.json            단계별 진행 기록 (어느 사이트가 몇 번째에 성공했는지 포함)
└─ _debug/               실패 시점 스크린샷·HTML
```

## 프롬프트 작성 규칙

`prompts/article_prompt.txt`를 수정해서 사용합니다. `{topic}` 자리에 주제가 들어갑니다.
에이전트가 응답을 해석하려면 아래 출력 형식이 들어 있어야 합니다.

```
[TITLE] 제목
[TAGS] 태그1, 태그2
```html
...본문 HTML... (이미지 위치에 <!-- IMAGE_1 --> ~ <!-- IMAGE_6 -->)
```
[IMAGE_PROMPT_1] ...
...
[IMAGE_PROMPT_6] ...
[END]
```

거절을 줄이는 요령:
- "검색해서", "링크에 들어가서", "이미지를 만들어서" 같은 **행동 지시**를 빼고, 필요한 자료는 프롬프트에 직접 붙여 넣으세요.
- 이미지는 글 작성 단계에서 **만들라고 하지 말고 프롬프트 텍스트만** 출력하게 하세요 (생성은 2단계에서 따로 합니다).
- "AI 티 안 나게", "탐지 우회" 대신 "친근한 구어체, 짧은 문단" 같은 문체 지시를 쓰세요.
- 의료·금융 효과를 단정하는 표현("무조건 낫는다")은 필터에 걸리기 쉽습니다.

이미지 위치 표시가 없으면 첫 이미지는 도입 문단 뒤에, 나머지는 소제목 앞에 고르게 자동 배치합니다.
이미지 프롬프트가 6개보다 적으면 주제를 기반으로 한 기본 프롬프트로 채웁니다.

## 스마트에디터 변환 규칙

| 원본 | 변환 |
|---|---|
| `h1`~`h4` | 굵게 + 글자 크기(28/24/19/16px) 문단 → 소제목처럼 표시 |
| `strong`/`em` | `b`/`i` |
| `blockquote` | 기울임 인용 문단 |
| `ul`/`ol`/`table`/`a(http)` | 유지 |
| `div`/`section`/`class`/`id`/`script`/`style`/외부 `img` | 제거 |

본문은 이미지 위치를 기준으로 조각을 나누고, `HTML 붙여넣기 → 이미지 업로드 → HTML 붙여넣기 …` 순서로 입력합니다.
기본값은 **임시저장**입니다. 발행까지 자동으로 하려면 `naver.publish: true`로 바꾸세요.

## 사이트가 바뀌어 멈췄을 때

1. `python -m blog_agent check` → `FAIL` 항목 확인
2. `output/<주제>/_debug/`의 스크린샷과 HTML에서 실제 요소 확인
3. `selectors.yaml`에 새 셀렉터를 **후보 목록 맨 앞에 추가** (코드 수정 불필요)

## 구조

```
blog_agent/
├─ __main__.py         명령줄 (run / chrome / check / convert / lint)
├─ pipeline.py         4단계 흐름 + 이어서 실행
├─ writer.py           글 작성: 거절 감지 → 새 대화 재시도 → 안내문 추가 → 다른 사이트로 전환
├─ refusal.py          거절/끊김 판정, 프롬프트 위험 표현 점검
├─ article.py          응답 → 제목/HTML/이미지 프롬프트/태그
├─ images.py           이미지 6장 (사이트 순차 대체, 있는 번호는 건너뜀)
├─ naver_converter.py  HTML → 스마트에디터용 조각
├─ naver_publisher.py  스마트에디터 입력/이미지 업로드/임시저장·발행
├─ providers/          gemini / chatgpt / flow 화면 조작
├─ browser.py          실제 크롬 CDP 접속
├─ dom.py              입력·붙여넣기·이미지 저장·디버그 덤프
├─ storage.py          주제 폴더, state.json
└─ config.py
selectors.yaml         사이트별 셀렉터 (UI 변경 시 여기만 수정)
```

## 테스트

```bash
python -m pytest -q
```
