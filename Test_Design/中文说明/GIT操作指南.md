# Git 操作指南

适用场景：你平时直接在 `main` 上改代码并推送，不额外创建本地分支。

## 1. 先进入项目目录

```bash
cd 你的项目目录
```

## 2. 查看当前分支和改动

最常用的就是这几个命令：

```bash
git branch --show-current
git status -sb
git diff
```

说明：
- `git branch --show-current`：看你现在在哪个分支
- `git status -sb`：看当前有哪些改动，格式比较简洁
- `git diff`：看具体改了什么

如果你只想快速确认自己是不是在 `main`，先跑：

```bash
git branch --show-current
```

如果输出是 `main`，就说明你现在就在主分支上。

## 3. 直接在 main 上提交并推送

这是你最常用的流程。

### 第一步：先切到 main

```bash
git switch main
```

### 第二步：先拉一下最新 main

```bash
git pull --ff-only origin main
```

### 第三步：改完代码后检查改动

```bash
git status -sb
git diff
```

### 第四步：提交

```bash
git add 路径1 路径2
git commit -m "简短说明这次修改"
```

如果你想一次把当前所有已修改文件都加进去，也可以用：

```bash
git add .
git commit -m "简短说明这次修改"
```

### 第五步：直接推到 main

```bash
git push origin main
```

## 4. 如果 push 失败

常见原因是远端 `main` 比你的本地更新。

这时先执行：

```bash
git pull --rebase origin main
git push origin main
```

如果有冲突，就先解决冲突，然后再：

```bash
git add 冲突文件
git rebase --continue
git push origin main
```

## 5. 如果你说的“覆盖 main”是强制覆盖远端

这个和正常 `push` 不是一回事。

正常直接提交到 `main` 用的是：

```bash
git push origin main
```

如果你真的要用本地内容强行覆盖远端 `main`，才用：

```bash
git push --force origin main
```

这个命令风险很大，因为它会直接改写远端 `main` 的历史。  
除非你非常确定要这样做，否则不要随便用。

## 6. 最简版日常流程

```bash
git branch --show-current
git switch main
git pull --ff-only origin main
git status -sb
git add .
git commit -m "简短说明"
git push origin main
```
