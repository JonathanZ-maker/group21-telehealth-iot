# 🚀 GETTING_STARTED — 第一次 clone 仓库后该做什么

> 面向每一位组员。读完这一页（3 分钟）就能开始干活。

---

## 1. Clone 仓库到你的电脑

```bash
git clone git@github.com:<our-org>/group21-telehealth-iot.git
cd group21-telehealth-iot
```

> 没装 `git` 的先装 git；没配 SSH key 的用 HTTPS 也行：
> `git clone https://github.com/<our-org>/group21-telehealth-iot.git`

## 2. 建 Python 虚拟环境 + 装依赖

```bash
python -m venv .venv
source .venv/bin/activate          # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. 配环境变量

```bash
cp .env.example .env
# 然后用任何编辑器打开 .env，填上真实值。
# 千万不要把 .env 提交到仓库（.gitignore 已经挡了）
```

## 4. 打开你自己的 TASKS 文档

根目录 `README.md` 里有"任务分工表" — 找到你的名字，点进你的 `TASKS_*.md`。你的任务 + 交付物 + 截止时间全在里面。

## 5. 建你自己的分支

**不要直接往 `main` 推**。为每个改动建一个分支：

```bash
git checkout -b feat/<your-name>-<short-topic>
# 比如
# git checkout -b feat/lkk-wearable-sim
# git checkout -b feat/yyx-cloud-api
# git checkout -b feat/lyz-hmac
# git checkout -b feat/zym-pydantic-test
```

## 6. 写代码 → commit → push → Pull Request

```bash
# 写完一小段就 commit，commit message 要清楚
git add .
git commit -m "feat(gateway): implement HMAC verification"
git push origin feat/lyz-hmac
```

push 之后 GitHub 会给你一个链接，点它 → "Create Pull Request"。PR 描述里 @ 一下受影响目录的 owner（见 `.github/CODEOWNERS`）让他们看一眼就能合并。

## 7. 每天早上先 pull

```bash
git checkout main
git pull origin main
git checkout feat/<your-branch>
git merge main            # 把别人的改动合进你的分支
```

---

## 🚦 三条必须遵守的纪律

1. **不要改别人目录下的文件**。有需要先在组群里说一声。
2. **commit 用你自己的 GitHub 账户** —— IPAC 评分就看 git blame。
3. **秘密永远不进仓库** —— MongoDB URI、HMAC 密钥、JWT 密钥都放 `.env`，不是代码里。

---

## ❓ 我不知道怎么办时

- 不知道这个目录是干嘛的 → 看那个目录下的 `README.md` 或 `TASKS_*.md`
- 代码报 "ModuleNotFoundError" → 是不是没激活 venv？`source .venv/bin/activate`
- 不知道怎么和别人模块对接 → 看 `zym_defense/INTEGRATION.md`（ZYM 的模块）或 `docs/DATA_CONTRACT.md`（数据格式）
- 还是不行 → 群里问，别硬扛
