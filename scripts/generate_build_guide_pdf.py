#!/usr/bin/env python3
"""Generate Adapt Labs build & release guide PDF."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUTPUT = Path(__file__).resolve().parent.parent / "Adapt-Labs-Build-and-Release-Guide.pdf"

MARGIN_L = 18
MARGIN_R = 18
MARGIN_T = 28
MARGIN_B = 18
HEADER_H = 14
BODY_W = 210 - MARGIN_L - MARGIN_R  # A4 mm


class AdaptGuidePDF(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(0, 0, 0)
        self.set_y(10)
        self.cell(0, HEADER_H, "Adapt Labs", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.4)
        y = self.get_y() + 1
        self.line(MARGIN_L, y, 210 - MARGIN_R, y)
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

    def section_title(self, title: str) -> None:
        self.ln(2)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(0, 0, 0)
        self.multi_cell(BODY_W, 8, title)
        self.ln(2)

    def sub_title(self, title: str) -> None:
        self.ln(1)
        self.set_font("Helvetica", "B", 11)
        self.multi_cell(BODY_W, 6, title)
        self.ln(1)

    def body(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(0, 0, 0)
        self.multi_cell(BODY_W, 5.5, text)
        self.ln(1)

    def bullet(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        x = self.get_x()
        self.cell(5, 5.5, "-")
        self.set_x(x + 5)
        self.multi_cell(BODY_W - 5, 5.5, text)
        self.ln(0.5)

    def code_block(self, text: str) -> None:
        self.set_font("Courier", "", 9)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(0, 0, 0)
        for line in text.strip().split("\n"):
            self.cell(BODY_W, 5, "  " + line, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_font("Helvetica", "", 10)

    def note(self, text: str) -> None:
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(60, 60, 60)
        self.multi_cell(BODY_W, 5, "Note: " + text)
        self.ln(1)
        self.set_text_color(0, 0, 0)


def build_pdf() -> Path:
    pdf = AdaptGuidePDF()
    pdf.set_auto_page_break(auto=True, margin=MARGIN_B)
    pdf.set_left_margin(MARGIN_L)
    pdf.set_right_margin(MARGIN_R)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "Adapt App", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, "Build binaries & publish to GitHub", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.body(
        "This guide explains how to package the Adapt App as a standalone executable "
        "with PyInstaller, for Linux and Windows, and how to upload both builds to "
        "GitHub Releases so friends can download them without installing Python."
    )

    # ---- LINUX ----
    pdf.add_page()
    pdf.section_title("Part 1 - Linux binary (PyInstaller)")
    pdf.body(
        "You develop on Linux (e.g. Fedora). The goal is a folder your users can "
        "extract and run without Python installed. Adapt App entry point: "
        "python -m src.core.main"
    )

    pdf.sub_title("1.1 Prerequisites")
    pdf.bullet("Python 3.11+ and git")
    pdf.bullet("Project folder cloned from GitHub")
    pdf.bullet("System libraries for pygame/SDL (Fedora example below)")
    pdf.code_block(
        "sudo dnf install python3-pip python3-devel SDL2 SDL2_image SDL2_mixer SDL2_ttf\n"
        "cd \"Adapt App\"\n"
        "python -m venv venv\n"
        "source venv/bin/activate\n"
        "pip install -e \".[dev]\""
    )

    pdf.sub_title("1.2 Create adapt.spec (one-time)")
    pdf.body(
        "The old main.spec points at Backend/Core/main.py and is outdated. "
        "Create adapt.spec in the project root:"
    )
    pdf.code_block(
        "# adapt.spec - save in project root\n"
        "block_cipher = None\n"
        "from PyInstaller.utils.hooks import collect_all\n"
        "pg_datas, pg_binaries, pg_hidden = collect_all('pygame')\n"
        "\n"
        "a = Analysis(\n"
        "    ['src/core/main.py'],\n"
        "    pathex=['.'],\n"
        "    binaries=pg_binaries,\n"
        "    datas=[('NeuroMods', 'NeuroMods')] + pg_datas,\n"
        "    hiddenimports=['pandas', 'fsrs', 'pygame', 'sqlite3'] + pg_hidden,\n"
        "    noarchive=False,\n"
        ")\n"
        "pyz = PYZ(a.pure)\n"
        "exe = EXE(\n"
        "    pyz, a.scripts, [], exclude_binaries=True,\n"
        "    name='AdaptApp', console=True,\n"
        ")\n"
        "coll = COLLECT(exe, a.binaries, a.datas, name='AdaptApp')"
    )
    pdf.note(
        "NeuroMods/ must be bundled - the bar game and flashcard import depend on it. "
        "Large image folders make the build big (~hundreds of MB); that is normal."
    )

    pdf.sub_title("1.3 Build")
    pdf.code_block(
        "source venv/bin/activate\n"
        "pyinstaller adapt.spec --noconfirm"
    )
    pdf.body("Output folder: dist/AdaptApp/")
    pdf.body("Test before uploading:")
    pdf.code_block("./dist/AdaptApp/AdaptApp")

    pdf.sub_title("1.4 Linux edge cases")
    pdf.bullet(
        "Missing NeuroMods: if the bar trainer says it cannot find NeuroMods/Bar, "
        "check datas= in adapt.spec includes ('NeuroMods', 'NeuroMods')."
    )
    pdf.bullet(
        "Database writes: adaptations.db lives at src/adaptations.db in dev. "
        "Frozen builds use sys._MEIPASS (read-only). For production, copy an empty "
        "DB to ~/.local/share/AdaptApp/ on first run, or document that users run "
        "from a writable folder."
    )
    pdf.bullet(
        "Wayland / KDE maximize crash: if the bar game segfaults on launch, try "
        "SDL_VIDEODRIVER=x11 ./dist/AdaptApp/AdaptApp or run windowed (F11)."
    )
    pdf.bullet(
        "Fonts: install liberation-sans-fonts for readable bar UI text on Fedora."
    )
    pdf.bullet(
        "One-file vs one-folder: this guide uses one-folder (faster startup, easier "
        "to debug). --onefile is possible but slower to start and harder to patch."
    )
    pdf.bullet(
        "glibc: build on an older distro (or CI with manylinux) if friends use "
        "older Linux - binaries linked against too-new glibc won't run elsewhere."
    )

    pdf.sub_title("1.5 Package for upload")
    pdf.code_block(
        "cd dist\n"
        "tar -czvf AdaptApp-linux-x86_64.tar.gz AdaptApp/"
    )

    # ---- WINDOWS ----
    pdf.add_page()
    pdf.section_title("Part 2 - Windows binary (for a non-technical friend)")
    pdf.body(
        "Your friend does not need to understand Python. They only need to build on "
        "a Windows PC (or you build in CI) and send you the zip. Give them this "
        "checklist verbatim."
    )

    pdf.sub_title("2.1 What your friend needs")
    pdf.bullet("Windows 10 or 11")
    pdf.bullet("Internet to download two installers (Python + Git - optional if you send a zip)")
    pdf.bullet("The Adapt App project folder (Download ZIP from GitHub)")

    pdf.sub_title("2.2 Step-by-step for your friend")
    pdf.body("Step 1 - Install Python")
    pdf.bullet("Go to https://www.python.org/downloads/")
    pdf.bullet("Download Python 3.11 or newer")
    pdf.bullet('Run installer. CHECK "Add python.exe to PATH" at the bottom - important!')
    pdf.bullet("Click Install Now")

    pdf.body("Step 2 - Open Command Prompt in the project folder")
    pdf.bullet("Unzip Adapt App to Desktop\\Adapt App")
    pdf.bullet("In the folder, click the address bar, type cmd, press Enter")

    pdf.body("Step 3 - Copy and paste these commands one block at a time")
    pdf.code_block(
        "python -m venv venv\n"
        "venv\\Scripts\\activate\n"
        "pip install -e \".[dev]\""
    )
    pdf.body("Step 4 - Create adapt.spec")
    pdf.body(
        "Copy the adapt.spec contents from Part 1.2 into a new file named adapt.spec "
        "in the project root (Notepad: File > Save As > adapt.spec, save as All Files)."
    )
    pdf.body("Step 5 - Build")
    pdf.code_block("pyinstaller adapt.spec --noconfirm")
    pdf.body("Wait several minutes. When done, the app is in dist\\AdaptApp\\AdaptApp.exe")

    pdf.body("Step 6 - Test")
    pdf.bullet("Double-click dist\\AdaptApp\\AdaptApp.exe")
    pdf.bullet("Choose 5 for Bar practice - window should open")
    pdf.bullet("If Windows SmartScreen warns: More info > Run anyway (unsigned exe)")

    pdf.body("Step 7 - Zip and send to you")
    pdf.bullet("Right-click dist\\AdaptApp folder > Send to > Compressed (zipped) folder")
    pdf.bullet("Email / Google Drive / Discord - send AdaptApp-windows.zip")

    pdf.sub_title("2.3 Windows edge cases")
    pdf.bullet(
        "Antivirus false positives: unsigned PyInstaller exes are often flagged. "
        "Build on a clean machine; upload SHA256 checksums on GitHub."
    )
    pdf.bullet(
        "Missing DLL / pygame: if the exe fails immediately, reinstall with "
        "pip install -e \".[dev]\" and rebuild; ensure collect_all('pygame') is in spec."
    )
    pdf.bullet(
        "Path with spaces: project folder name Adapt App is fine; always quote paths in scripts."
    )
    pdf.bullet(
        "Long paths: enable Windows long path support if build fails on deep NeuroMods paths."
    )

    # ---- GITHUB ----
    pdf.add_page()
    pdf.section_title("Part 3 - Publish Linux & Windows on GitHub")
    pdf.body(
        "Use GitHub Releases so users download a zip, extract, and run - no git or pip."
    )

    pdf.sub_title("3.1 Prepare release assets")
    pdf.bullet("AdaptApp-linux-x86_64.tar.gz (from Part 1.5)")
    pdf.bullet("AdaptApp-windows.zip (from your friend's Part 2)")
    pdf.bullet("Optional: SHA256 checksums text file for both")

    pdf.sub_title("3.2 Create a release on GitHub")
    pdf.bullet("Open your repo on github.com")
    pdf.bullet("Click Releases (right sidebar) > Create a new release")
    pdf.bullet("Choose a tag, e.g. v0.0.1-alpha - Create new tag on publish")
    pdf.bullet("Release title: Adapt App v0.0.1-alpha")
    pdf.bullet("Describe what's new (bar trainer, customer portraits, etc.)")

    pdf.sub_title("3.3 Upload binaries")
    pdf.bullet("Drag both archives into Attach binaries")
    pdf.bullet("Publish release")

    pdf.sub_title("3.4 README snippet for users")
    pdf.code_block(
        "## Downloads\n"
        "Get the latest release for your system:\n"
        "- **Linux**: AdaptApp-linux-x86_64.tar.gz\n"
        "  tar -xzf AdaptApp-linux-x86_64.tar.gz && ./AdaptApp/AdaptApp\n"
        "- **Windows**: AdaptApp-windows.zip\n"
        "  Extract and run AdaptApp.exe"
    )

    pdf.sub_title("3.5 Ongoing releases")
    pdf.bullet("Tag each release (v0.0.2, etc.) - never overwrite old tags")
    pdf.bullet("Build Linux binary yourself; friend rebuilds Windows when you ask")
    pdf.bullet("Or use GitHub Actions later to build both automatically on push tag")

    pdf.sub_title("3.6 Edge cases on GitHub")
    pdf.bullet(
        "100 MB limit per file on free GitHub - if NeuroMods makes the zip huge, "
        "consider Git LFS or splitting asset packs."
    )
    pdf.bullet(
        "License: ensure LICENSE allows redistribution of bundled NeuroMods images."
    )
    pdf.bullet(
        "Do not commit dist/ or build/ - add to .gitignore; only upload Release assets."
    )

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Quick reference", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "Linux build:  pip install -e \".[dev]\" && pyinstaller adapt.spec\n"
        "Linux run:    ./dist/AdaptApp/AdaptApp\n"
        "Windows run:  dist\\AdaptApp\\AdaptApp.exe\n"
        "Dev run:      python -m src.core.main"
    )

    pdf.output(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    path = build_pdf()
    print(f"Wrote {path}")