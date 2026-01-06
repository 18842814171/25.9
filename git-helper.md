#  Git Large-File Cleanup & “hung up unexpectedly” Troubleshooting Guide

This guide covers:

1. **Preventing unwanted files**
2. **Removing already-uploaded files**
3. **Retrying commits & pushes safely**
4. **Diagnosing “remote hung up unexpectedly”**

---

## 1️⃣ Prevent unwanted files from being committed (BEFORE problems)

### Use `.gitignore` correctly

`.gitignore` only affects **future tracking**, not history.

Common ignores for Windows / Visual Studio / class projects:

vim .gitignore
```gitignore
# IDE / cache
.vs/
**/.vs/
*.ipch
*.suo
*.db

# Build output
build/
out/
Debug/
Release/
x64/
x86/

# Documents / binaries
*.pdf
*.doc
*.docx
*.ppt
*.pptx
*.zip
*.exe
```

👉 **Rule of thumb**
Source code → OK
Build artifacts / Office files / datasets → ❌ Don’t commit

---

## 2️⃣ Remove files that were ALREADY committed (most important)

If a file was **ever committed**, `.gitignore` is **too late**.

### 🔥 Correct tool: `git filter-repo`

> `git rm` only affects the current commit
> `git filter-repo` rewrites **all history**

### Remove by file type (recommended)

```bash
git filter-repo --force \
  --path-glob "*.pdf" --invert-paths \
  --path-glob "*.docx" --invert-paths \
  --path-glob "*.ppt*" --invert-paths \
  --path-glob "*.zip" --invert-paths \
  --path-glob "*.in" --invert-paths \
  --path .vs --invert-paths
```

### Remove a specific file or directory

```bash
git filter-repo --force \
  --path path/to/bigfile --invert-paths
```

---

## 3️⃣ Verify cleanup BEFORE pushing (critical step)

### Check repository size

```bash
git count-objects -vH
```

**Healthy repo**

```
size-pack: < 100 MB (often 20–80 MB)
```

If still large → something big remains in history.

---

### Confirm a file is gone from history

```bash
git log --all -- path/to/file
```

No output = file fully removed.

---

## 4️⃣ Retry push correctly after history rewrite

Because history changed, you **must force push**:

```bash
git push origin main --force
```

⚠️ This is safe **only** if:

* You are the only contributor
* You intentionally rewrote history

---

## 5️⃣ Diagnose “remote end hung up unexpectedly”

This error has **three common causes**:

---

### ❌ Cause A — GitHub file size limits

Symptoms:

* Push runs for a long time
* Ends with:

  ```
  remote: GH001: Large files detected
  fatal: The remote end hung up unexpectedly
  ```

Rules:

* **100 MB per file (hard limit)**
* Repo size can be large, but **single files cannot**

✅ Fix:

* Remove files from history with `git filter-repo`

---

### ❌ Cause B — Network / SSH blocked (very common on campus networks)

Symptoms:

```bash
ssh -T git@github.com
Connection reset by xx.xx.xx.xx port 22
```

Meaning:

* Port 22 is blocked
* NOT a Git or GitHub problem

#### Fix 1 (best): SSH over port 443

```text
# ~/.ssh/config
Host github.com
  Hostname ssh.github.com
  Port 443
  User git
```

#### Fix 2: Use HTTPS

```bash
git remote set-url origin https://github.com/USER/REPO.git
git push origin main --force
```

(Use a GitHub Personal Access Token as password.)

---

### ❌ Cause C — Pushing too much at once

Symptoms:

* Very slow compression
* Timeouts

Mitigations:

```bash
git config --global pack.window 0
git config --global pack.depth 0
```

(But this is **secondary**; large files are the real cause.)

---

## 6️⃣ Mental model (remember this)

| Situation                 | Correct tool       |
| ------------------------- | ------------------ |
| Prevent future junk       | `.gitignore`       |
| Remove tracked files now  | `git rm --cached`  |
| Remove files from history | `git filter-repo`  |
| History rewritten         | `git push --force` |
| SSH blocked               | SSH-443 or HTTPS   |

---

## 7️⃣ Golden rules to avoid this forever

1. **Never commit build output or IDE cache**
2. **Never commit Office files or datasets**
3. **Check `git status` before every commit**
4. **If GitHub rejects once, stop and diagnose**
5. **Large files → history rewrite, not retry**


#  Git Recovery Guide: Computer Powered Off During Commit / Push

## 0️⃣ First: don’t panic (Git is crash-safe)

Git is **transactional**:

* A commit is either **fully written or not written at all**
* A push either **reaches the remote or it doesn’t**

A sudden poweroff **almost never corrupts committed history**.

---

## 1️⃣ After reboot: assess the local state (DO THIS FIRST)

Run these commands in order:

```bash
git status
git log --oneline --decorate -5
git reflog
```

### What you’re checking:

* Is your working tree clean?
* Did the commit actually happen?
* Where does `HEAD` point now?

---

## 2️⃣ Scenario A — Commit DID succeed, push failed (most common)

### Symptoms

* `git log` shows your new commit
* `origin/main` is behind
* Files are “green” locally but not on GitHub

### Action

```bash
git push origin main
```

If it hangs or fails → go to **Section 5**.

---

## 3️⃣ Scenario B — Commit did NOT succeed

### Symptoms

* Files still appear in `git status`
* No new commit in `git log`

### Action

```bash
git add <files>
git commit -m "message"
git push origin main
```

---

## 4️⃣ Scenario C — Commit half-finished / editor crashed

Rare, but possible.

### Symptoms

* Git complains about a commit in progress
* `.git/COMMIT_EDITMSG` exists

### Fix

```bash
git commit --abort
```

Then restart cleanly:

```bash
git add <files>
git commit -m "message"
```

---

## 5️⃣ Scenario D — Push hangs or says “remote end hung up unexpectedly”

This is **NOT** caused by the poweroff itself.

### Common causes (ranked)

1. **Large files** (>50–100 MB)
2. **Network interruption**
3. **SSH blocked (port 22)**

---

## 6️⃣ Diagnose push failures properly

### Step 1 — Look for large files

```bash
git push origin main
```

If you see:

```text
GH001: Large files detected
remote end hung up unexpectedly
```

➡ You committed large files.
**Retrying will never work.**

---

### Step 2 — Check repo size

```bash
git count-objects -vH
```

Large `size-pack` → history contains big files.

---

### Step 3 — Fix large files (if needed)

```bash
git filter-repo --force --path-glob "*.zip" --invert-paths
```

(Repeat for other unwanted types.)

---

## 7️⃣ Scenario E — SSH suddenly stops working after reboot

### Symptom

```bash
ssh -T git@github.com
Connection reset by ... port 22
```

### Cause

* Network blocks SSH (very common on campus / ISP networks)

### Fix (recommended)

Use SSH over HTTPS port 443:

```text
# ~/.ssh/config
Host github.com
  Hostname ssh.github.com
  Port 443
  User git
```

Or switch to HTTPS.

---

## 8️⃣ Final retry checklist (SAFE order)

After cleanup:

```bash
git status
git log --oneline -3
git count-objects -vH
git push origin main --force   # only if history was rewritten
```

---

## 9️⃣ What NOT to do

❌ Don’t keep retrying a failed push without reading the error
❌ Don’t assume `.gitignore` removes committed files
❌ Don’t delete `.git` hoping it fixes things
❌ Don’t reclone until you understand what failed

---

## 🔑 Key mental model (remember this)

| Event                  | Impact                               |
| ---------------------- | ------------------------------------ |
| Poweroff during commit | Commit aborted or safe               |
| Poweroff during push   | Local repo safe                      |
| Green files locally    | Commit exists locally                |
| Not on GitHub          | Push never succeeded                 |
| “hung up” error        | Almost always large files or network |

---

## ✅ One-sentence takeaway

> **A poweroff doesn’t break Git; retrying blindly does — always inspect `status`, `log`, and error messages before pushing again.**
