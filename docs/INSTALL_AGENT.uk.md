# Встановлення через Codex або іншого локального агента

Цільовий профіль: Windows 10/11 + WSL2 Ubuntu 22.04, NVIDIA CUDA GPU; також Linux із сумісним стеком. Скрипти не встановлюють Windows-драйвер, WSL чи CUDA toolkit автоматично. На новому ПК потрібен повний контрольний прогін; не плутати успішний pip install із готовою генерацією.

## 1. Перевірки перед встановленням

1. Прочитай AGENTS.md. Перевір власне місцезнаходження репозиторію, права запису та доступ до мережі.
2. Windows: `wsl -l -v`, `nvidia-smi`; WSL: `nvidia-smi`, `nvcc --version`, `free -h`, `df -h`. GPU має бути доступний у WSL2. Linux NVIDIA driver у WSL не встановлювати поверх Windows driver.
3. Перевір версію Python, GPU compute capability і відповідність PyTorch/CUDA. Контрольний стек: Python 3.10, torch 2.4.1+cu121, torchvision 0.19.1+cu121, CUDA toolkit 12.1; ML constraints у `constraints-ml.txt`. Профіль GTX 1060 — architecture 6.1.
4. Знайди наявні Hunyuan, venv, toolkit і Hugging Face cache. Якщо вони сумісні, задай їх у `.env`; не копіюй приватні значення в публічні файли. Наявний venv викликай його Python напряму.
5. Потрібні build-essential, git, python3.10-venv, Python headers, libGL/libglib, nvcc та достатньо RAM/SSD. Для Ubuntu 22.04 базові пакети: `sudo apt-get install git build-essential python3.10-venv python3.10-dev libgl1 libglib2.0-0`. CUDA toolkit встановлюй за офіційною інструкцією NVIDIA для WSL, підібраною під GPU. Це системна зміна, може потребувати адміністратора.

Джерела: [NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html), [Hunyuan installation](https://github.com/Tencent-Hunyuan/Hunyuan3D-2#install), [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/). Перевір актуальність команд перед встановленням системного ПЗ.

## 2. Структура та налаштування

Скопіюй `.env.example` у `.env`. За замовчуванням upstream/venv/ваги будуть у `~/.local/share/local-3d-workshop`, виходи — `runtime/` біля коду. У `.env` використовуй Linux-шляхи, навіть якщо запускаєш Start-Local.ps1. Папка репозиторію може бути на диску Windows; важкі venv і build бажано тримати в Linux filesystem.

`.env` завантажує `run.sh`. При окремих командах встановлення/doctor/download задай `set -a; source .env; set +a` (тільки якщо .env існує) або передай змінні в середовищі. `config.py` читає змінні середовища, не сам файл `.env`.

## 3. Runtime

У WSL/Linux з кореня репозиторію:

```bash
bash install-wsl.sh
```

Скрипт клонує офіційний Hunyuan на відтворюваному commit `f8db63096c8282cb27354314d896feba5ba6ff8a`, створює venv, ставить залежності та збирає rasterizer/render extension для фактичної GPU. Існуючий upstream з іншим commit він не скидає. Після першого встановлення не запускай скрипт без потреби: перевір doctor і використай наявне середовище.

За нестандартного CUDA встанови CUDA_HOME/PATH; для GTX 1060 задай `TORCH_CUDA_ARCH_LIST=6.1`, `MAX_JOBS=2`. Не використай готовий rasterizer wheel без перевірки архітектури. Помилка `no kernel image is available` означає необхідність збирання для правильної GPU. Якщо nvcc не бачить CUDA headers, перевір toolkit та include-шляхи PyTorch NVIDIA packages; не змінюй їх наосліп.

`apply_offload_patch.py` виправляє переміщення prompt embeddings між CPU й CUDA та зберігає резервну копію вихідного файла. Після зміни dynamic pipeline старий процес треба завершити перед новим запуском; чистити можна лише відповідний dynamic-code cache, не весь Hugging Face cache. Agent має підтвердити сумісність patch з upstream.

## 4. Ваги

Використовуй Python саме створеного venv, із PYTHONPATH на upstream. За типовими шляхами:

```bash
export HUNYUAN_HOME="$HOME/.local/share/local-3d-workshop/Hunyuan3D-2"
export PYTHONPATH="$HUNYUAN_HOME"
"$HUNYUAN_HOME/.venv/bin/python" download_models.py
"$HUNYUAN_HOME/.venv/bin/python" doctor.py
```

Завантажуються mini Turbo, 2mv та Paint v2.0 без Turbo із delight. Офіційний Hugging Face cache повторно використовується; retry зберігає часткові завантаження. Для економії можна `download_models.py --models multiview paint`. Перевір ліцензії моделей; за потреби користувач сам проходить login/accept terms. Не друкуй токени в лог.

## 5. Запуск і контроль

Windows: `powershell -ExecutionPolicy Bypass -File .\Start-Local.ps1`; Linux/WSL: `bash run.sh`. Якщо змінено порт, вкажи його також у n8n workflow. Не запускай другу службу на вже зайнятому порту. Health: `http://localhost:7861/api/health`, API docs: `/api/docs`.

Після запуску перевір:

- Python syntax і `check_queue.py` (ніякої GPU-генерації).
- Health, українську вебформу, preview трьох завантажених фото, state queued та залежний Paint.
- Один повний mesh/Paint smoke run на референсі користувача. Не запускай його без референсу чи непомітно як частину doctor: це тривала обробка.
- Читання `textured.glb` через trimesh, повні UV і texture, чотири ракурси preview. Запиши параметри, тривалість та peak VRAM.

n8n необов'язковий: встановлюй за його актуальною офіційною документацією, створи власний owner account, імпортуй `n8n/workflow.json`, активуй production webhook і задай URL у `.env`. Не копіюй чужі database, credential export або стандартні паролі. Невдалий n8n webhook не означає, що генерація зупинилася.

## 6. Якщо не працює

Порт не відповідає: прочитай runtime/service-error.log, перевір WSL і процес uvicorn. OOM: перевір FP16/offload, сторонні GPU-процеси й RAM; не запускай Paint паралельно з shape. На 90% GPU може бути 0% через CPU UV-inpaint; перевір CPU/process перш ніж переривати. Несумісні нові GPU потребують іншого PyTorch/toolkit та нового smoke run; контрольний стек не є гарантією для всіх карт.

У фінальному звіті агента зазначай, що встановлено/перевірено, адресу сервісу й реальні обмеження. Не називай setup завершеним, якщо моделі чи native kernels не перевірені.
