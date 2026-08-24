<div align="center">

[English](README.md) · [中文](README.zh-CN.md)

# Jianyang Skills

**在真实工作流中跑通过，并带有测试、边界和可安装源码的小型 Agent Skills。**

</div>

如果你有一本本地、无 DRM 的电子书，希望在 Kindle 上获得干净排版、正确书名/作者/封面，又不想失去字体选择和原始文件，这里的首个 Skill 就是为这个问题准备的。它适合 Kindle 读者，尤其是仍可通过 USB 挂载的旧设备；输出包括检查过的衍生文件、哈希、质检报告和分闸传输路径。你可以一条命令安装，查看下面的可重复证据，最后仍以真实 Kindle 的显示为准。

```bash
npx skills add https://github.com/jianyangzhai/jianyang-skills --skill kindle-ebook-preflight
```

<!-- attribution:start -->
由 [Jianyang Zhai](https://github.com/jianyangzhai) 制作与维护 · [@jianyangzhai](https://github.com/jianyangzhai) · [jianyang-skills](https://github.com/jianyangzhai/jianyang-skills)
<!-- attribution:end -->

## 首个 Skill

### [Kindle Ebook Preflight](kindle-ebook-preflight/README.md)

检查、规范化、目视复核并安全传输用户本地提供的 EPUB、MOBI、AZW 或 AZW3，同时保留 Kindle 的字体和阅读控制。

它会提供：

- EPUB/MOBI 结构检查和明确的 DRM 阻断；
- 规范化 EPUB、AZW3/KF8，以及可选的 MOBI6 兼容版本；
- 读者控制型或保留原布局型排版；
- 封面、目录、章节、图片、注释和末章复核闸门；
- SHA-256 绑定审批、原子 USB 复制和已验证的书库缩略图；
- 机器可读 manifest 与人类可读报告。

## 证据

当前 macOS 本地证据：

- 14 项使用合成可再分发样书的确定性检查全部通过；
- 检测到 W3C EPUBCheck 5.3.0 与 Calibre 9.13.0；
- EPUB→AZW3 和 MOBI6 round-trip 路径通过；
- 生成的 EPUB/AZW3 中维护者品牌字符串为 0。

这些证据不能替代在目标 Kindle 上打开最终文件，检查字体切换、目录、图片/注释和末章。

## 安装

上面的命令使用开放 Agent Skills 格式，并且只选择 `kindle-ebook-preflight`。`skills` CLI 默认记录匿名安装遥测；如需退出：

```bash
DISABLE_TELEMETRY=1 npx skills add https://github.com/jianyangzhai/jianyang-skills --skill kindle-ebook-preflight
```

安装前也可以直接查看 [SKILL.md](kindle-ebook-preflight/SKILL.md)。运行要求是 Python 3.10+、W3C EPUBCheck 与 Calibre；USB 直传要求 Kindle 能以大容量存储方式挂载。

如果希望先下载并审查公开仓库，再从本地副本安装：

```bash
git clone https://github.com/jianyangzhai/jianyang-skills.git
npx skills add ./jianyang-skills --skill kindle-ebook-preflight
```

ClawHub/OpenClaw 当前不可用：ClawHub 的 MIT-0 发布规则与本 Skill 的 GPL-3.0-only 许可证冲突。只有解决许可证冲突、取得单独批准并验证真实公开页面后，才会启用下面的预定安装命令：

```bash
openclaw skills install @jianyangzhai/kindle-ebook-preflight
```

在真实 ClawHub 页面验证成功前，不要把这条命令当成已可用。

## 其他公开项目

这些项目继续保留自己的仓库和历史：

- [Idea Darwin](https://github.com/jianyangzhai/idea-darwin)——通过结构化变异和选择迭代想法。
- [De-AI Writing](https://github.com/jianyangzhai/de-ai-writing)——清理中文文本中模式化的 AI 写作痕迹。
- [Resume De-AI](https://github.com/jianyangzhai/resume-de-ai)——在不牺牲专业度的前提下审查简历中的 AI 化表达。

## 信任边界

- 不搜索或下载图书。
- 不移除或绕过 DRM。
- 不覆盖原始文件或 Kindle 上的另一版本。
- 没有在网上找过匹配的正式版本并取得明确批准，不生成替代封面。
- 没有隐藏遥测、跟踪像素或第三方上传。可选的局域网传书只会在明确授权后提供一个哈希已批准文件，并绑定到显式指定的本机局域网地址。
- 维护者署名只出现在文档和质检报告中，不进入电子书正文、封面、书名、作者、目录、内部 metadata 或 Kindle 缩略图。

参见 [SECURITY.md](SECURITY.md)、[CONTRIBUTING.md](CONTRIBUTING.md) 和 [ATTRIBUTIONS.md](ATTRIBUTIONS.md)。

## 关于

本仓库是 [Jianyang Zhai](https://github.com/jianyangzhai) 制作与维护的 Agent Skills 公开发行面。每个版本都从独立的唯一源生成，发布前完成验证，并通过 [@jianyangzhai](https://github.com/jianyangzhai) 回链到这里。

## 许可证

根目录文档采用 MIT。每个 Skill 可以有自己的许可证；`kindle-ebook-preflight` 当前为 `GPL-3.0-only`，因为它的缩略图帮助程序在 Calibre 中运行并导入 Calibre 模块。以距离文件最近的 `LICENSE` 为准。
