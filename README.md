# Rookie File Organizer

A small Flask web app that accepts a folder upload, organizes files according to the selected rules, writes logs, and returns a zip archive of the organized result.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

## Upload behavior

Use the folder picker in the browser. The app uses the selected folder name, size, and file tree to build an organized zip archive after organization succeeds.
