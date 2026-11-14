# docs/ —— 发布用的成品文件

这里放的是**给 GitHub 直接看**的成品，源头在仓库外层的 `.archify/` 目录（那些 review-*/、截图、finalize 回执都是过程证据，不进仓库）。

| 文件 | 说明 | 来源 |
|---|---|---|
| `index.html` | 策略流程图，单文件自包含（无外部 JS/CSS/图片依赖） | `.archify/architecture-a-kill-strategy-20261103-200500/a-kill-strategy.html` |
| `a-kill-candidate.json` | 流程图的源描述文件 | 同上目录 |

## 改完图之后要同步一次

`.archify/` 里的按钮是 archify 的 finalize 命令（会跑视觉校验），生成新的 `a-kill-strategy.html` 后，把两个文件覆盖过来：

```powershell
$src = '.archify\architecture-a-kill-strategy-20261103-200500'
Copy-Item "$src\a-kill-strategy.html"   'docs\index.html'            -Force
Copy-Item "$src\a-kill-candidate.json"  'docs\a-kill-candidate.json' -Force
```

`docs/index.html` 与 `.archify/.../a-kill-strategy.html` 内容应当逐字节一致，只是放在能被 GitHub Pages 直接托管的位置。
