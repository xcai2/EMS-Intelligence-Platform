# Git 操作指南

git branch
# 查看本地分支
# 带 * 的是你当前所在分支

git fetch
# 先更新远程分支信息到本地
# 不会改你的代码内容，只是让你看到最新远程状态

git branch -r
# 查看远程分支

git branch -a
# 查看所有分支
# 包括本地分支 + 远程分支

git branch -vv
# 查看本地分支 + 当前分支 + 每个本地分支跟踪的远程分支

git switch 分支名
# 切换到一个“本地已经存在”的分支

git switch -c 新分支名
# 创建一个新的本地分支，并立刻切换过去

git switch -c 本地分支名 --track origin/远程分支名
# 当远程有这个分支、但本地还没有时
# 在本地创建一个跟踪远程分支的新分支，并切换过去

git pull
# 拉取并更新当前分支的远程内容
# 一般是在你已经切到某个分支之后再用

git status -sb
# 查看当前分支状态
# 包括当前在哪个分支、是否有修改、是否和远程同步


git log --oneline main..origin/main
# 看远程 main 比你本地 main 多了哪些提交
# 如果这里有输出，说明远程 main 变了，你本地还没跟上

git log --oneline origin/main..main
# 看你本地 main 比远程 main 多了哪些提交
# 如果这里有输出，说明你本地比远程多提交

git diff main origin/main
# 看本地 main 和远程 main 的代码内容差异

```bash
git push
真正把当前本地分支的提交推到远程
```

想要更新最新的 `main`

```bash
git branch          # 查看当前分支
git status          # 查看当前分支状态（是否有未提交改动）

# 如果有未提交改动，先临时保存
git stash -u

git fetch origin    # 同步远程信息，不直接改本地代码
git switch main     # 切换到本地 main
git pull origin main # 同步远程 main 到本地 main
```

推送本地更新后的分支 / 新分支

```bash
git switch -c feature/news-filter-ui-update   # 新建并切换到新分支
git add .                                     # 添加本次修改
git commit -m "Update news filtering and news page UI"   # 提交本地修改
git push -u origin feature/news-filter-ui-update         # 首次推送到远程并建立跟踪关系
```