# GitHub 仓库搭建手把手指南（给 ZYM）

> 读完这份文档就能从 0 把仓库建起来并推动组员上线。总耗时 15–20 分钟。

---

## 📋 你需要做的事情总览

1. 下载我给你的 zip，解压到本地
2. 在 GitHub 上建一个 **private** 仓库
3. 在本地用 `git init` 把解压后的文件推上去
4. 把组员加为 collaborator
5. 把下面那段微信/群消息发给组员

---

## Step 1：解压 zip 到本地

1. 下载 `group21-telehealth-iot-repo.zip`
2. 解压到一个你记得住的位置，比如 `~/projects/group21-telehealth-iot`
3. 打开终端（macOS: Terminal / Windows: PowerShell 或 Git Bash）：

```bash
cd ~/projects/group21-telehealth-iot
ls
```

应该看到 `README.md`、`zym_defense/`、`docs/` 等一堆文件/目录 → 对了就下一步。

---

## Step 2：在 GitHub 建仓库

1. 登录 GitHub → 右上角 `+` → **New repository**
2. 填：
   - **Owner**：你的账户（推荐）或者 team org（如果组里已经有）
   - **Repository name**：`group21-telehealth-iot`
   - **Description**：`UCL ELEC0138 Group 21 — Privacy-Preserving Telehealth IoT System`
   - **Private** ✅（开发期保持 private，**提交前一周改 public**）
   - **不要**勾 "Add a README"（我们已经有了）
   - **不要**勾 "Add .gitignore"（我们已经有了）
   - **不要**选 license（我们已经有了 MIT）
3. 点 `Create repository`
4. 页面跳转后 **保持这个页面**，一会儿要复制里面的命令

---

## Step 3：本地初始化 git 并推上去

**关键：先检查你的 git 身份**（这个名字会显示在每次 commit 上，是 IPAC 评分的依据）：

```bash
git config --global user.name          # 看一下叫什么
git config --global user.email         # 看一下邮箱

# 如果是错的（比如是默认 "your name"），改成你真实的：
git config --global user.name  "Your Real Name"
git config --global user.email "your.email@ucl.ac.uk"    # 用和 GitHub 绑定的邮箱
```

然后在项目目录里：

```bash
cd ~/projects/group21-telehealth-iot

# 初始化
git init
git branch -M main

# 第一次提交
git add .
git status                     # 瞄一眼，确认没有 .env 或 __pycache__
git commit -m "chore: initial repository scaffolding"

# 关联远端（下面这行从 GitHub 页面复制；大概长这样）
git remote add origin git@github.com:<你的用户名>/group21-telehealth-iot.git

# 推上去
git push -u origin main
```

如果 SSH 报错，改用 HTTPS：
```bash
git remote set-url origin https://github.com/<你的用户名>/group21-telehealth-iot.git
git push -u origin main
# 会让你输用户名和 personal access token（不是密码）
```

> 没有 personal access token？GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic) → 勾 `repo` 权限 → 生成后复制（只会显示一次）

刷新 GitHub 仓库页面 → 应该看到所有文件。

---

## Step 4：加组员为 collaborator

在 GitHub 仓库页面：

1. `Settings` → `Collaborators` → `Add people`
2. 输入三个组员的 **GitHub 用户名** 或 **邮箱**
3. 权限选 **Write**（不要给 Admin）
4. 他们邮箱会收到邀请，点接受就能看到仓库

> ⚠️ 如果组员不想/没有 GitHub 账号，让他们**现在就注册一个**，用学校邮箱，用真实姓名 —— 评审助教会点进每个 commit 看是谁推的。

---

## Step 5：（推荐）保护 main 分支

`Settings` → `Branches` → `Add branch protection rule`：
- Branch name pattern：`main`
- 勾 `Require a pull request before merging`
- 勾 `Require approvals` = 1

这样任何人都不能直接推 `main`，必须走 PR，有一个简单的同行 review 机制。**IPAC 会看到你的 PR 和 review 记录**，这也是贡献证据。

---

## Step 6：通知组员 — 直接把下面这段复制发出去

---

**给组员的群消息（直接复制）：**

> 大家好，Group 21 的 GitHub 仓库建好了：
> 
> **链接**：https://github.com/<你的用户名>/group21-telehealth-iot
> 
> **请每个人现在做三件事：**
> 
> 1. 接受我发到你邮箱的 collaborator 邀请
> 2. `git clone` 仓库到本地，**先完整读一遍 `GETTING_STARTED.md`**（3 分钟）
> 3. 然后根据 `README.md` 里的分工表找到你的任务文档，开始干活
> 
> 关键纪律：
> - 不要直接推 `main`，每个人建自己的 `feat/<你名>-<任务>` 分支
> - commit 用实名账户（IPAC 评分要的）
> - 秘密（MongoDB URI、密钥）永远只放 `.env`，不要进代码
> - 有疑问先看目录下的 `TASKS_*.md` 或 `README.md`，再问群里
> 
> 截止：4 月 24 日 16:00（还剩 7 天）。有问题 @ 我。

---

## 📅 接下来的仓库节奏建议

| 时间 | 动作 | 谁 |
|------|------|-----|
| 今天 | 仓库建好，组员全部接收邀请 | 你 + 组员 |
| 今天-明天 | Phase 0：wearable → gateway → cloud 基础流水线跑通 | LKK / LYZ / YYX |
| 4/19 | 两个攻击脚本可复现 | LKK + YYX |
| 4/20-4/21 | 防御全部集成 + 截图 | 你 + LYZ |
| 4/22 | 实验跑完 + 图生成 | 你 + LKK |
| 4/23 | 报告初稿 + 录视频 | 全组 |
| 4/24 晨 | 最终 PDF + 把仓库改 public + 填个人贡献 | 全组 |
| 4/24 16:00 | 提交 Moodle | 组长 |

---

## 🔧 仓库改 public 的步骤（最后一天做）

仓库页面 → `Settings` → 最底下 `Danger Zone` → `Change repository visibility` → Public → 按提示确认两次。

这时候要确保：
- [ ] `.env` 绝对不在仓库里（有 `.gitignore` 挡着，应该没事）
- [ ] 没有硬编码的密钥（搜一下 `grep -r "mongodb+srv://" . --exclude-dir=.git`）
- [ ] 没有涉及隐私的真实病人数据（只用 Kaggle / PhysioNet 公开数据）
- [ ] `README.md` 的项目链接指向正确
