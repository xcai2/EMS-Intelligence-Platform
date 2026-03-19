# Git 操作速查（本项目）

## 1. 查看当前分支和状态

```bash
# 当前所在分支
git branch --show-current

# 所有本地分支（* 号为当前分支）
git branch

# 当前分支和远端关系 + 改动摘要
git status -sb
```

---

## 2. 更新到远端最新代码

```bash
cd /Users/gao/Desktop/Flex-Practicum-Project-2026
git fetch origin
git pull --rebase origin main
```

如果你的主分支不是 `main`，把 `main` 换成你的分支名。

---

## 3. 新建功能分支（推荐）

```bash
cd /Users/gao/Desktop/Flex-Practicum-Project-2026
git checkout -b feat/your-change-name
```

示例：

```bash
git checkout -b feat/big5-ui-update
```

---

## 4. 提交本地改动

```bash
# 查看改动
git status

# 添加改动
git add .

# 提交
git commit -m "Update Big Five CapEx page UI"
```

---

## 5. 推送到 GitHub

```bash
# 第一次推送这个新分支
git push -u origin feat/your-change-name

# 之后继续推送
git push
```

---

## 6. 发起 PR（Pull Request）

推送后到 GitHub 仓库页面：

1. 点击 `Compare & pull request`
2. 选择 `base: main`，`compare: feat/your-change-name`
3. 填写标题和描述并创建 PR

---

## 7. 如果你已经在 main 上改了代码，怎么补救

在不丢改动的情况下切到新分支：

```bash
git checkout -b feat/your-change-name
git add .
git commit -m "Your commit message"
git push -u origin feat/your-change-name
```

---

## 8. 临时保存改动（stash）

```bash
# 暂存当前改动
git stash

# 拉最新代码
git pull --rebase origin main

# 恢复改动
git stash pop
```

查看 stash 列表：

```bash
git stash list
```

---

## 9. 常用检查命令

```bash
# 查看提交历史
git log --oneline --decorate -n 15

# 查看某次提交内容
git show <commit_id>

# 查看当前改了哪些文件
git diff --name-only
```

---

## 10. 最常用安全流程（建议记住）

```bash
cd /Users/gao/Desktop/Flex-Practicum-Project-2026
git fetch origin
git pull --rebase origin main
git checkout -b feat/your-change-name
git add .
git commit -m "Describe your change"
git push -u origin feat/your-change-name
```

