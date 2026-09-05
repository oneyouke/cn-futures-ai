# Windows 运行指南

1. 从 https://www.python.org/downloads/windows/ 安装 Python 3.10 或更新版本。若安装器提供 Add python.exe to PATH，请勾选。
2. 打开 https://github.com/oneyouke/cn-futures-ai/tree/codex/initial-backtest ，点击 Code → Download ZIP。
3. 完整解压到普通目录（例如 C:\\cn-futures-ai），不要直接在 ZIP 内运行。
4. 双击 run_windows.bat。它会检查 Python 版本，运行测试，再执行合成行情演示，最后保留窗口显示结果。
5. 查看 results 文件夹中的 summary.json、trades.csv 和 equity.csv。再次运行会覆盖此目录中的同名结果。

此步骤不需要恒力期货账户、API 权限或联网行情，不会登录账户或下单。当前尚未实现实时模拟交易和 AI 模型。

若显示 Python 未找到，安装后重新运行；若显示错误，把错误文字或截图发来，不要包含密码。启动器使用英文提示以减少 Windows 终端编码问题。

也可以在解压目录的终端中运行：

```bat
python futures.py --test
python futures.py --demo
```

真实数据格式和本地合约配置详见 README.md。恒力期货接口类型、权限及测试环境仍需客户经理确认。
