# Beginner installation: RTX 5090 to Hermes Desktop

This guide assumes you have a Windows PC with an NVIDIA GeForce RTX 5090 and
have never installed a local AI model before. You will use normal graphical
installers for the prerequisites, paste three lines into Command Prompt, choose
a model profile (stock remains recommended), and accept the download and Hermes prompts.

At the end:

- Docker Desktop runs NInfer, the program that uses the RTX 5090 to generate
  answers.
- Stock Hermes Desktop runs as a normal Windows application.
- Hermes uses NInfer on this PC as its configured AI model provider.
- There is no project username or password, and no cloud AI account or API key
  is required.

NInfer is prepared before Hermes. This avoids opening Hermes with a local
provider that does not work yet.

## Before you begin

You need:

- an NVIDIA GeForce RTX 5090;
- a supported 64-bit Windows installation;
- a working internet connection for the first setup;
- at least 24 GiB free for the recommended stock profile, or 21 GiB for the
  optional uncensored profile;
- additional free space in Docker Desktop's storage for the Linux image and
  temporary build files.

The stock NInfer artifact is approximately 20.02 GiB and the uncensored
artifact is approximately 16.96 GiB. Docker image storage is separate. Close
games and other GPU-heavy programs before loading the model.

## 1. Install the four prerequisites

Use each product's normal graphical installer. You do not need to type any
PowerShell, Bash, WSL, pip, uv, or CUDA commands.

### NVIDIA driver

1. Open the [official NVIDIA driver page](https://www.nvidia.com/en-us/drivers/).
2. Select the RTX 5090 and your Windows version.
3. Install the current driver and restart Windows if asked.

You do **not** need the separate CUDA Toolkit. NInfer's required CUDA software
is provided by its Docker image.

### Docker Desktop

1. Follow the [official Docker Desktop for Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/).
2. Use the recommended per-user installation and Linux-container backend.
3. Keep the recommended WSL 2 backend if Docker selects it. Docker manages that
   backend; this project never asks you to open WSL.
4. Start Docker Desktop after installation and accept its terms if they are
   appropriate for your use.
5. You may close it afterward. Setup starts Docker Desktop and waits for its
   engine when needed.

Docker Desktop must remain running whenever you use the local model in Hermes.
You do not need to sign in to Docker Hub to build this project, although Docker
Desktop's license terms still apply.

### Git

1. Install [Git for Windows](https://git-scm.com/download/win).
2. Its normal installer defaults are sufficient.

### Python

1. Install 64-bit [Python for Windows](https://www.python.org/downloads/windows/),
   version 3.10 or newer.
2. Enable the option to add Python to `PATH` if the installer offers it.
3. Close any Command Prompt window that was open before the installation.

The project does not install packages into Python and does not use pip. Python
only runs the cross-platform `ninfer.py` setup helper.

## 2. Clone the project

Press the Windows key, type **Command Prompt**, and open it normally. Do not
choose **Run as administrator**. Then enter:

```text
git clone https://github.com/joelfourhman/hermes_ninfer_stack.git hermes-ninfer-stack
cd hermes-ninfer-stack
```

The first line downloads this small project. It does not download the AI model.
The second line moves Command Prompt into the project directory. The setup
command initializes the exact NInfer source automatically, so no Git submodule
knowledge is required.

If Windows says `git` is not recognized, close and reopen Command Prompt. If it
still fails, rerun the Git installer before trying the clone again.

## 3. Run the one-command setup

Enter:

```text
python ninfer.py setup
```

If Windows says `python` is not recognized, close and reopen Command Prompt. If
it still fails, rerun the Python installer and enable its PATH option.

Keep Command Prompt open until it says Hermes is configured. The setup is
resumable, so rerunning the same command is safe if Windows restarts or the
internet connection is interrupted. Before downloading the model, setup checks
Python, Git, available disk space, the RTX 5090, Docker Compose, and
Linux-container mode. If Docker Desktop is installed but stopped, setup opens
it and waits for its engine. If anything is missing, it gives a plain-English
fix and stops before the large download.

### Model choice and download prompt

The menu lists the supported models with their download size and decoder
capabilities from the [generated reference](generated-config.md). On a fresh
installation, press Enter for the recommended stock model. Select uncensored
only if you specifically want reduced refusal behavior. The optional
stock-dflash2 companion is a separate artifact for decoder experiments, with
additional storage and GPU memory costs; it is not the default.

Setup next describes the selected transfer and asks whether to download it.
Press Enter to accept yes. Nothing large is downloaded until you
consent.

The shared downloader uses a committed uv lock inside a temporary, CPU-only
Docker container. It does not use pip or install Python packages on Windows.
No Hugging Face account or token is required for the public models. Artifacts
are pinned to immutable repository revisions and validated against
their published byte size and SHA-256. The old model file remains available
when switching. Setup does not continue to
Hermes until the selected model produces a short authenticated answer.

Fresh setup uses the balanced RTX 5090 runtime with shared KV and host prefix
retention, and matches Hermes's context/compression settings to it. Exact
capacities are in the generated profile table. Existing selected profiles are
preserved when setup is rerun.

If you type `n` at the download prompt, setup stops cleanly. Run
`python ninfer.py setup` again when you are ready for the download.

To change profiles later without repeating Hermes setup, run:

```text
python ninfer.py select-model
```

To choose without an interactive prompt, pass the model with `--model`:

```text
python ninfer.py select-model --model stock
python ninfer.py select-model --model uncensored
```

It preserves existing artifacts and restores the old profile if the selected one
does not pass its live test.

To change performance/context behavior without downloading another model, run:

```text
python ninfer.py select-runtime
```

For example, explicitly select the recommended default with:

```text
python ninfer.py select-runtime --profile balanced
```

Do not use `--profile stock`: `--profile` belongs to runtime selection, while
`select-model` uses `--model`.

The recommended balanced profile is the default. Choose `single-session` for
one isolated lane or `max-context` for a 240K ceiling. The selector verifies
the new service, rolls back on failure, and updates Hermes automatically.

### Hermes Desktop prompt

Once NInfer is working, setup asks:

```text
Install and configure stock Hermes Desktop now? [Y/n]:
```

Press Enter. The capital `Y` means yes is already the default.

If Hermes is not installed, your browser opens the
[official Hermes Desktop page](https://hermes-agent.nousresearch.com/desktop).
Then:

1. Choose the Windows download on the official page.
2. Run the stock Hermes installer and complete its normal per-user setup. This
   repository does not download, wrap, or replace that installer.
3. Start Hermes once if the installer does not open it automatically.
4. If Hermes asks which AI provider to use, select **Choose provider later**.
   Do not enter a Nous Portal key or another cloud-provider key for this local
   setup.
5. Let Hermes finish installing its components and complete the first-launch
   screens.
6. Return to the still-running Command Prompt. At **Press Enter here after
   those three steps are finished**, press Enter.

The helper now stores a randomly generated local connection key in Hermes's
normal private settings and selects the local `qwen-local` model. It does not
show the key, ask you to copy it, or change unrelated Hermes providers and
preferences. It also selects Hermes's `manual` command-approval mode so flagged
commands are shown to you instead of being automatically approved by the
default smart reviewer. It leaves the working directory at the stock Hermes
default instead of forcing this repository's `workspace/`. File and terminal
tools have your normal user access, subject to Hermes's built-in protected-path
rules.

Wait for this message:

```text
Hermes Desktop is configured for the authenticated local NInfer endpoint.
```

The helper next says **Close Hermes Desktop if it is open, then press Enter to
reopen it**. Close the Hermes window, return to Command Prompt, and press Enter.
The helper reopens Hermes automatically when it can; otherwise it tells you to
use the Start menu. Wait for **SETUP COMPLETE**, then begin a new chat.

A simple first message such as
`Reply with one sentence to confirm you are working` is enough to confirm the
desktop experience. Before allowing Hermes to run commands or change files,
read
[Safety before the first real task](#safety-before-the-first-real-task).

## If the Hermes window or setup window was closed

The completed model does not need to be downloaded again. Open Command Prompt in the
`hermes-ninfer-stack` directory and run:

```text
python ninfer.py install-hermes
```

This command starts Docker Desktop and the configured NInfer service if needed,
opens the official Hermes page if the stock app is still missing, and safely
repeats only the Hermes configuration.

If the model setup itself did not finish, use the original resumable command:

```text
python ninfer.py setup
```

## Optional confidence check

After Hermes is configured, close Hermes and run:

```text
python ninfer.py verify
```

This checks the local model checksum and provenance, RTX 5090 access, NInfer authentication, a
real generated answer, Hermes's selected provider, and the complete
Hermes-to-NInfer route. Initial model loading can take several minutes. To see
NInfer's current output while diagnosing a wait, run:

```text
python ninfer.py logs
```

Press Ctrl+C when you are finished viewing the output; that stops the log view,
not the NInfer container.

For a concise, prompt-safe report of recent latency, throughput, cache reuse,
queue timeouts, and context failures, run:

```text
python ninfer.py diagnose-performance
```

## Using Hermes after restarting Windows

The selected model remains on disk. You do not repeat setup.

1. Open Command Prompt in the `hermes-ninfer-stack` directory.
2. Start NInfer:

   ```text
   python ninfer.py up
   ```

   This starts Docker Desktop if needed and waits until the model is ready.

3. Open Hermes Desktop from the Start menu.

To stop the local model when you are finished:

```text
python ninfer.py down
```

Stopping NInfer does not remove the model or Hermes chats. Closing Hermes does
not stop NInfer. Docker Desktop needs to stay open only while NInfer is running.

## Safety before the first real task

Hermes Desktop runs as your signed-in Windows user. That means it can read or
change the same files that you can, without needing an Administrator prompt.
UAC does not protect your normal user files from another program running as
you.

If you selected the uncensored profile, it has substantially reduced refusal
behavior. That is a behavior change, not a permission or safety feature. It can
attempt requests the stock model might decline, so keep manual approvals
enabled and do not treat a confident answer as evidence that an action is safe.

For a safer beginning:

- never run Hermes as Administrator;
- create or clone a normal project folder for each task and tell Hermes which
  folder to use, just as with a stock installation;
- read approval prompts before allowing file or command actions;
- remember that approving a Docker command gives Hermes the same Docker access
  as your signed-in user;
- keep important files in version control or a backup Hermes cannot overwrite;
- do not enable unattended tools, plugins, or scheduled actions until you
  understand their access.

Hermes approvals are useful guardrails, but native Hermes is not an operating
system sandbox. Use a separate Windows account or virtual machine if you need a
stronger boundary. Read [Security](security.md) before granting broad tool
access.

## What setup changes

Setup creates an ignored `.env` file containing the private NInfer key and
saves the model under `models/`. Only NInfer receives GPU access, and the model
and container root filesystem are read-only; only bounded temporary memory is
writable. Fresh setup listens only at the private `127.0.0.1` loopback
address. Trusted-LAN access remains off until explicitly enabled with
`python ninfer.py network --mode lan`.

## Optional access from another LAN computer

After setup is healthy, run:

```text
python ninfer.py network --mode lan
```

Choose the host's private IPv4 interface and confirm the warning. Then run
`python ninfer.py network` to show the endpoint and
`python ninfer.py network --show-key` to reveal the bearer key deliberately.

Install Hermes Desktop and copy or clone this repository on each client. Select
the backend preset on the NInfer host first, then configure the same named preset
on the client:

```text
# NInfer host
python ninfer.py use autonomous
python ninfer.py network --mode lan
python ninfer.py network --show-key

# LAN client; use the endpoint printed by `network`
python ninfer.py configure-client autonomous --endpoint http://192.168.1.20:8080/v1
```

The client command prompts for the bearer key without placing it in shell
history, verifies the authenticated `qwen-local` endpoint, creates or updates
the native `ninfer-autonomous` Hermes profile and makes it active. Restart Hermes
Desktop afterward. Pass `--no-activate` to prepare the profile without switching.
Repeat with `default`, `coding`, `coding-fast`, `research`, `low-vram` or
`uncensored` as needed.

One NInfer host serves one backend preset at a time. The preset selected with
`use` on the host and the active `ninfer-*` profile on every client must match.

LAN mode is intended only for a trusted private network. Do not configure a
router port forward. If required, create a host firewall allowance limited to
the Private profile, the selected TCP port, and the local subnet. Restore the
default with `python ninfer.py network --mode local`.

The official Windows Hermes installation normally keeps its runtime under
`%LOCALAPPDATA%\hermes`. Its current stock installer internally invokes its own
PowerShell bootstrap and provisions PortableGit. This project never asks you
to run either shell, but a policy that forbids those installer-managed
processes is not compatible with the current stock Hermes distribution.

When upgrading from this repository's former all-container release, setup may
remove its obsolete Hermes, relay, and SSH-sandbox containers as Compose
orphans. It also backs up `.env` and removes only the obsolete legacy
container/dashboard/model-builder variables. It does not delete ignored host
data or named volumes.

## Updating

Treat NInfer and Hermes as independent programs:

- update Hermes with its official Desktop update mechanism;
- update this repository only after reviewing its release and compatibility
  notes;
- rerun `python ninfer.py install-hermes` after changing the NInfer key, port,
  or model;
- rerun `python ninfer.py verify` after either side changes.

The helper does not silently replace or downgrade an existing Hermes Desktop
installation.

## Uninstalling

- Use Windows's normal installed-apps page to uninstall Hermes Desktop. Decide
  separately whether to keep its user data.
- Run `python ninfer.py down` to stop NInfer.
- Docker image cleanup and deletion of `models/` are separate, explicit
  actions. Setup never deletes a downloaded model or old rollback model.

For other failures, continue with [Troubleshooting](troubleshooting.md).

The optional DFlash2 companion artifact is a third explicit selection with additional disk/VRAM costs. See [models](models.md) and the [generated sizes/checksums](generated-config.md).
