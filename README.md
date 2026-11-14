# G8 Compat Patcher

GameSir G8 Galileo의 컨트롤러 이름 프로필을 적용할 업데이트 ZIP을 만드는 Windows 도구입니다.

## 지원 모델과 프로필

USB-C형 **G8 Galileo**, 공식 원본 **129.60-1.5**를 지원합니다. G8+와 다른 모델에는 사용하지 마세요.

| 프로필 | Android 모드 | PS 모드 |
| --- | --- | --- |
| Kishi + Xbox | Razer Razer Kishi Ultra | Xbox Wireless Controller |
| Kishi + PS | Razer Razer Kishi Ultra | Wireless Controller |

프로필은 장치 이름과 식별 정보를 변경합니다. PS 모드의 입력 형식은 유지되며, Windows XInput으로 변환하지 않습니다.

Kishi + Xbox 프로필의 PS 모드는 실제 Xbox 패드처럼 L2·R2를 아날로그 축으로만 보내고 버튼 신호는 보내지 않습니다. 이름을 보고 Xbox 배치를 적용하는 게임에서 트리거를 누를 때 조작 방식이 터치와 패드 사이를 오가는 문제를 막기 위한 것입니다. L2·R2를 버튼으로만 읽는 앱에는 Kishi + PS 프로필을 사용하세요.

## 사용법

1. [Releases](https://github.com/CodeKi0303/g8-compat-patcher/releases/latest)에서 Windows ZIP을 내려받아 압축을 풉니다.
2. `G8-Compat-Patcher.exe`를 실행합니다.
3. **GameSir 공식 서버에서 자동 다운로드**를 선택합니다. 원본 ZIP이 있으면 **이미 받은 공식 ZIP 선택**으로 불러올 수 있습니다.
4. 프로필과 저장 폴더를 선택하고 **업데이트 ZIP 만들기**를 누릅니다.
5. 생성된 ZIP을 휴대폰으로 복사합니다. 파일명을 바꾸거나 압축을 풀지 마세요.
6. G8를 **매핑 모드**로 연결하고 GameSir 앱의 **로컬 펌웨어**에서 ZIP을 선택합니다.
7. 업데이트가 끝나면 G8를 분리했다 다시 연결한 뒤 Android 또는 PS 모드로 전환합니다.

원본과 결과 파일은 자동으로 검증합니다. 원본이 지원 버전과 다르거나 다운로드에 실패하면 ZIP을 만들지 않습니다.

- 다운로드한 원본은 저장 폴더의 `originals`에 보관됩니다.
- 내부 버전은 `129.60-1.5`로 유지됩니다. 생성된 ZIP 파일명의 버전은 업데이트 선택용입니다.
- 이 도구는 파일 생성만 지원합니다. PC에서 직접 설치하거나 기기 내부를 백업하지 않습니다.

## Python으로 실행

Python 3.11 이상이 필요합니다. GUI에는 Tkinter가 필요합니다.

```console
python -m g8_patcher
python -m g8_patcher build --download --profile kishi-xbox --output-dir output
python -m g8_patcher build --source original.zip --profile kishi-ps --output-dir output
```

테스트는 `python -m unittest discover -s tests -v`로 실행합니다. Windows 배포본은 `requirements-build.txt`를 설치한 환경에서 `scripts/build-windows.ps1`로 빌드합니다.

## 라이선스

패처 코드는 [MIT](LICENSE)입니다. 배포 파일에는 펌웨어가 포함되지 않으며, 원본은 사용자의 PC에서 GameSir 서버로부터 받습니다. 원본·생성 펌웨어와 제품명에 대한 권리는 해당 권리자에게 있습니다. [외부 구성요소 고지](THIRD_PARTY_NOTICES.md)를 확인하세요.
