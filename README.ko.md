# Agent Workflows

[English](README.md) | 한국어

> 이 문서는 [README.md](README.md)의 한국어 번역입니다. 두 문서의 내용이 다를
> 경우 영문 README가 기준입니다.

Codex, Claude Code, Antigravity, GitHub Copilot CLI, Cursor에서 함께 쓰는
에이전트 스킬 모음입니다.

`implementation-skill`은 이제 PyreWire로 평가되는 Wirelog 기반 하네스입니다.
호스트 진입점은 그대로 유지하면서, 구현 작업을 더 작은 원자적(atomic) 스킬로
나누고 요청마다 명시적인 규칙으로 스킬 계획을 선택합니다.

문서를 포함한 모든 변경은 검증되고, 독립적으로 리뷰되며, Architect와 Critic의
승인을 받은 뒤 하나의 원자적 단위로 커밋됩니다. 모든 실행은 결과를 보고하며,
커밋 전에 게이트에서 거부된 실행도 마찬가지입니다.

선택적 온톨로지 팩은 보안, 데이터 변경, 배포 검증을 추가합니다. 선택된 각 도메인
검사는 리뷰와 커밋 전에 실행되며, 정확히 해당 후보(candidate)에 대한 근거를
보고합니다. 필수 검증이 누락되면 커밋이 차단됩니다.

## 포함된 스킬

- `implementation-skill`: PyreWire를 통해 원자적 구현 스킬을 선택하는 Wirelog 기반 하네스 진입점입니다.
- `close-open-issues-goal`: 저장소의 열린 이슈를 0개로 줄이기 위한 지속형 워크플로입니다.

## 온톨로지 팩

```bash
agent-workflows-harness --list-ontology-packs
agent-workflows-harness --ontology-pack security --touches secret_handling --scope one_line
agent-workflows-harness --ontology-pack data-change --ontology-pack deployment --touches schema_migration --touches deployment_manifest
```

내장 ID나 로컬 JSON 파일을 지정하려면 `--ontology-pack` 인자를 반복해서
사용합니다. 팩은 기본 코어를 확장하거나, `--ontology`로 지정한 대체 베이스를
확장합니다. 의존성은 명시적으로 지정해야 합니다. 병합된 어휘는
`--print-ontology`로 확인할 수 있으며, 계획에는 `ontology_composition`과
`derived`에 관계 수준의 출처(provenance)가 포함됩니다.
[팩 구성과 저장소 확장 (영문)](docs/how-it-works.md#ontology-packs)을 참고하세요.

## 하네스 CLI

셀렉터를 로컬에서 실행하려면 Python 패키지를 설치합니다. 이 패키지는 안정적인
1.x API 계열 안에서 PyreWire 1.1.2 이상을 요구합니다.

```bash
python3 -m pip install -e ".[dev]"
```

그런 다음 스킬 계획을 선택합니다.

```bash
agent-workflows-harness "refactor auth workflow and add tests"
```

이 명령은 요청 사실(fact), 선택된 스킬, 차단된 스킬, 규칙 사유를 담은 JSON을
출력합니다. 실행에 대한 선택 기록을 영구적으로 남기려면
`--decision-log path/to/decisions.jsonl`을 추가합니다.

요청은 산문 대신 온톨로지 트리플로도 표현할 수 있습니다. 하네스는 선언된 클래스
계층에서 요청 속성을 추론하므로, 표면(surface)은 그것을 설명하는 단어가 아니라
그것이 *무엇인지*에 따라 인식됩니다.

```bash
agent-workflows-harness --touches session_module --scope one_line
```

`session_module`에는 텍스트 분류기가 아는 키워드가 하나도 없지만,
`AuthSurface ⊑ SharedBehavior` 덕분에 여전히 계획, 비평, 광범위 테스트가
선택됩니다. 추론된 각 속성은 그것을 만들어 낸 포함 관계(subsumption) 경로와 함께
보고됩니다. `--print-ontology`는 요청이 사용할 수 있는 어휘를 출력하므로,
`--touches`나 `--scope`에 쓸 이름을 추측하지 않고 직접 읽을 수 있습니다. 자체
TBox를 지정하려면 `--ontology path/to/tbox.json`을 사용합니다. 어휘 추가는 코드
변경이 아니라 데이터 변경이며, 지정한 파일이 어떻게 로드되었는지도 같은 플래그로
확인할 수 있습니다.
[동작 방식 (영문)](docs/how-it-works.md#ontology-fact-source)을 참고하세요.

`--graph DIR`은 실행 자체를 `agent-workflows-<UTC timestamp>.dot`이라는 이름의
Graphviz DOT 파일로 기록합니다. 이 파일에는 활성 TBox와 함께, 이 요청에서 도출된
속성과 선택되거나 차단된 스킬이 담깁니다. 디렉터리는 지정한 그대로 사용되며
파일 이름만 달라집니다. 값을 생략하면 시스템 임시 디렉터리에 기록합니다.

```bash
agent-workflows-harness --touches session_module --scope one_line --graph
# graph written: /tmp/agent-workflows-20260818T111907250000Z.dot
dot -Tsvg /tmp/agent-workflows-20260818T111907250000Z.dot -o run.svg
```

경로는 stderr로 보고되므로, stdout은 호출자가 파싱하는 JSON 문서로 유지됩니다.
[동작 방식 (영문)](docs/how-it-works.md#run-graph)을 참고하세요.

플러그인 호스트는 `PATH`, 현재 작업 공간의 `.venv`, 또는 import 가능한 활성
Python 환경 순서로 하네스를 찾습니다. 런타임을 사용할 수 없다고 판단하기 전에
가능한 모든 형태를 시도하며, 의존성을 설치하거나 호스트 환경을 자동으로 고쳐 쓰지
않습니다. 정확한 명령은
[설치 (영문)](docs/installation.md#harness-command-resolution)를 참고하세요.

GitHub Copilot CLI는 이 저장소에서 플러그인을 직접 설치할 수 있습니다.

```bash
copilot plugin install justinjoy/agent-workflows:plugins/dev-workflows
```

그런 다음 `/implementation-skill`을 사용하거나, Copilot에게
`implementation-skill` 스킬을 사용하라고 요청합니다. 플러그인의 `bin/` 런처
덕분에 저장소의 `.venv`가 `PATH`에 없어도 Copilot에서 하네스를 사용할 수 있습니다.

Cursor는 이 저장소의 `.cursor-plugin/marketplace.json`에서 플러그인을
가져옵니다(Customize를 연 뒤 From GitHub Repository 선택). 그런 다음
`/implementation-skill`을 사용합니다.
[설치 (영문)](docs/installation.md#cursor)를 참고하세요.

지원되는 PyreWire 휠에는 Wirelog 런타임이 포함되어 있습니다. `WIRELOG_LIB`는
번들된 라이브러리를 재정의하거나, 사용자 지정(custom) 또는 소스에서 빌드한 PyreWire 설치를 사용할 때만
필요합니다.

## 문서 (영문)

- [동작 방식](docs/how-it-works.md)
- [설치](docs/installation.md)
- [유지보수](docs/maintenance.md)

## 라이선스

APACHE-2.0
