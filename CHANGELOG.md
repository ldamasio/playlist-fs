Perfeito — aqui vai um **pacote v0 pronto pra commit**, com conteúdo inicial de todos os arquivos.

Você pode copiar e colar criando os arquivos nessa estrutura:

```text
playlist-fs/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── .gitignore
├── bin/
│   ├── music-init.sh
│   └── music-link
├── docs/
│   ├── design.md
│   └── examples.md
└── tests/
    └── smoke.sh
```

---

## `README.md`

````md
# playlist-fs

**Playlists as filesystem projections over a canonical music library.**

`playlist-fs` is a local-first, file-based toolkit where playlists are just symlinked filesystem views over a canonical music library.

No daemon.  
No cloud.  
No login.  
Just files + symlinks + shell.

---

## Philosophy

- Your music lives in one place: `~/Music/_library/Artist/Album/Track`
- Playlists are views: `~/Music/Playlists/<name>/` containing symlinks to tracks in `_library`
- New downloads go to `_incoming/` until you curate them

---

## Install

Clone and put scripts in your PATH.

Option A (recommended): symlink scripts into `~/.local/bin`:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/bin/music-init.sh" ~/.local/bin/music-init.sh
ln -sf "$PWD/bin/music-link"    ~/.local/bin/music-link
````

Make sure `~/.local/bin` is in PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## Quick start

Initialize your `~/Music` structure:

```bash
music-init.sh
```

Put music into:

```text
~/Music/_library/Artist/Album/Track.ext
```

Link tracks into playlists:

```bash
music-link "Tycho/Awake/01 - Awake.mp3" focus
music-link "Nils Frahm/Spaces/01 - An Aborted Beginning.flac" sleep
music-link "Daft Punk/Discovery/01 - One More Time.mp3" pleasure
```

Optional custom filename:

```bash
music-link "Tycho/Awake/01 - Awake.mp3" focus --name "tycho-awake.mp3"
```

---

## Docs

* Design: `docs/design.md`
* Examples: `docs/examples.md`

---

## Tests

Run the smoke test:

```bash
bash tests/smoke.sh
```
