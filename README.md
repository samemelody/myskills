# myskills

个人 Claude Code Skill 合集。

## music-score-digitizer

乐谱数字化工作流：将扫描/拍照的乐谱转换为 MusicXML、矢量 PDF 和参考音频。

两条路径：
- **AI 辅助转谱**（推荐）：源文件审计 → 逐系统裁切 → 多模态读谱 + 像素几何校验 → 和声仲裁 → 人工核验清单
- **传统 OMR**：OpenCV 预处理 → Audiveris → MuseScore 校正 → 导出

详见 [music-score-digitizer/SKILL.md](music-score-digitizer/SKILL.md)。
