"""Windows desktop research application; no network or broker login."""
import csv
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from dataclasses import asdict
from datetime import datetime
from futures import Config, backtest, demo


def run_research(csv_path='', config_path=''):
    if csv_path and not config_path:
        raise ValueError('真实行情回测必须选择合约配置 JSON。')
    config = Config(**json.loads(Path(config_path).read_text(encoding='utf-8-sig'))) if config_path else Config()
    if csv_path:
        with open(csv_path, encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            required = {'timestamp', 'trading_day', 'open', 'high', 'low', 'close'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError('CSV 缺少字段：' + ', '.join(sorted(required - set(reader.fieldnames or []))))
            bars = []
            for line, row in enumerate(reader, 2):
                try:
                    bars.append({**row, **{k: float(row[k]) for k in ('open', 'high', 'low', 'close')}})
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'CSV 第 {line} 行价格格式错误') from exc
    else:
        bars = demo()
    summary, trades, curve = backtest(bars, config)
    summary.update(synthetic_data=not bool(csv_path), config=asdict(config))
    return summary, trades, curve


def export_result(result, parent):
    # Unique directory prevents overwriting previous research runs.
    folder = Path(parent) / ('backtest-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True, exist_ok=False)
    summary, trades, curve = result
    (folder / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, rows, fields in [('trades', trades, ['timestamp','action','side','price','fee','realized_pnl','reason']), ('equity', curve, list(curve[0]))]:
        with (folder / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return folder


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('期货研究台 · 国内商品期货')
        self.geometry('1120x760')
        self.minsize(900, 640)
        self.configure(bg='#eef2f6')
        self.result = None
        self.mailbox = queue.Queue()
        self.csv_path = tk.StringVar()
        self.config_path = tk.StringVar()
        self.status = tk.StringVar(value='就绪 · 点击「运行演示」体验完整流程')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#eef2f6')
        style.configure('TLabel', background='#eef2f6', foreground='#203047')
        style.configure('TButton', padding=(12, 7))
        style.configure('Treeview', rowheight=28, font=('Microsoft YaHei UI', 9))
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 9, 'bold'))
        head = tk.Frame(self, bg='#13243a', padx=24, pady=18)
        head.pack(fill='x')
        tk.Label(head, text='期货研究台', bg='#13243a', fg='white', font=('Microsoft YaHei UI', 23, 'bold')).pack(side='left')
        tk.Label(head, text='离线回测  /  v0.2', bg='#13243a', fg='#a7c9df', font=('Microsoft YaHei UI', 11)).pack(side='right')
        main = ttk.Frame(self, padding=20)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='恒力期货接入待配置 · 当前不连接账户、不发送订单；AI 模型尚未接入。').pack(anchor='w', pady=(0, 12))
        for label, var in [('行情 CSV', self.csv_path), ('合约 JSON', self.config_path)]:
            row = ttk.Frame(main)
            row.pack(fill='x', pady=3)
            ttk.Label(row, text=label, width=11).pack(side='left')
            ttk.Entry(row, textvariable=var).pack(side='left', fill='x', expand=True, padx=8)
            ttk.Button(row, text='选择文件', command=lambda v=var: self.pick(v)).pack(side='left')
        actions = ttk.Frame(main)
        actions.pack(fill='x', pady=12)
        self.demo_btn = ttk.Button(actions, text='运行演示', command=lambda: self.start(True))
        self.demo_btn.pack(side='left')
        self.run_btn = ttk.Button(actions, text='回测所选行情', command=lambda: self.start(False))
        self.run_btn.pack(side='left', padx=8)
        ttk.Button(actions, text='保存配置示例', command=self.save_config).pack(side='left')
        self.export_btn = ttk.Button(actions, text='导出结果', command=self.export, state='disabled')
        self.export_btn.pack(side='right')
        self.metrics = tk.StringVar(value='运行回测后显示：期末权益 · 净收益 · 最大回撤 · 成交笔数')
        tk.Label(main, textvariable=self.metrics, bg='white', fg='#12465b', font=('Microsoft YaHei UI', 13, 'bold'), pady=16, padx=12, anchor='w').pack(fill='x')
        self.mode = tk.StringVar(value='演示数据和示例参数不代表真实合约或历史表现。')
        ttk.Label(main, textvariable=self.mode).pack(anchor='w', pady=8)
        tabs = ttk.Notebook(main)
        tabs.pack(fill='both', expand=True)
        chart_page = ttk.Frame(tabs)
        tabs.add(chart_page, text='  权益曲线  ')
        self.canvas = tk.Canvas(chart_page, bg='white', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        table_page = ttk.Frame(tabs)
        tabs.add(table_page, text='  成交记录  ')
        cols = ('timestamp','action','side','price','fee','realized_pnl')
        self.table = ttk.Treeview(table_page, columns=cols, show='headings')
        for col, label in zip(cols, ['时间','开平','买卖','价格','手续费','已实现盈亏（未扣费）']):
            self.table.heading(col, text=label)
            self.table.column(col, width=170 if col == 'timestamp' else 120, minwidth=80)
        scroll = ttk.Scrollbar(table_page, command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(fill='both', expand=True)
        help_page = ttk.Frame(tabs, padding=16)
        tabs.add(help_page, text='  使用说明  ')
        text = ('1. 初次使用点击「运行演示」，无需账户或网络。\n\n'
                '2. 真实 CSV 字段：timestamp,trading_day,open,high,low,close。\n'
                '    仅用单一实际合约；时间为无时区北京时间，交易日由行情源提供。\n\n'
                '3. 保存配置示例后，按真实合约乘数、价位、保证金和费用修改 JSON。\n'
                '    示例参数仅供演示。行情回测时必须选择配置文件。\n\n'
                '4. 回测完成后可查看曲线、成交并导出。每次导出创建新的文件夹。\n\n'
                '模型限制：信号及风控在收盘检查，下一开盘执行；末根收盘清仓。\n'
                '未模拟涨跌停排队、强平、结算、换月和真实交易日历。\n'
                '止损不保证最大亏损，结果只用于研究。')
        ttk.Label(help_page, text=text, wraplength=800, justify='left').pack(anchor='nw')
        ttk.Label(main, textvariable=self.status).pack(anchor='w', pady=(10, 0))
        self.after(100, self.poll)

    def pick(self, var):
        ext = '*.csv' if var is self.csv_path else '*.json'
        path = filedialog.askopenfilename(filetypes=[('数据文件', ext)])
        if path:
            var.set(path)

    def save_config(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='contract.local.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                Path(path).write_text(json.dumps(asdict(Config()), indent=2), encoding='utf-8')
                self.config_path.set(path)
                messagebox.showinfo('示例已保存', '示例全部为演示参数。使用真实行情前，请按目标合约修改。')
            except OSError as exc:
                messagebox.showerror('保存失败', str(exc))

    def start(self, synthetic):
        csv_path = '' if synthetic else self.csv_path.get().strip()
        config_path = '' if synthetic else self.config_path.get().strip()
        if not synthetic and not csv_path:
            messagebox.showerror('请选择行情', '请先选择行情 CSV 文件。')
            return
        self.result = None
        self.metrics.set('正在计算…')
        self.mode.set('合成行情演示' if synthetic else '所选 CSV 回测')
        self.table.delete(*self.table.get_children())
        self.draw()
        for button in (self.demo_btn, self.run_btn, self.export_btn):
            button.configure(state='disabled')
        self.status.set('计算中，请稍候…')
        def worker():
            try:
                self.mailbox.put((True, run_research(csv_path, config_path)))
            except Exception as exc:
                self.mailbox.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            ok, payload = self.mailbox.get_nowait()
        except queue.Empty:
            pass
        else:
            for button in (self.demo_btn, self.run_btn):
                button.configure(state='normal')
            if ok:
                self.show_result(payload)
            else:
                self.metrics.set('本次回测未完成')
                self.status.set('运行失败，请检查文件和配置')
                messagebox.showerror('回测失败', payload)
        self.after(100, self.poll)

    def show_result(self, result):
        self.result = result
        s, trades, curve = result
        self.metrics.set(f"期末权益 ¥{s['final_equity']:,.2f}    净收益 ¥{s['net_pnl']:,.2f}    最大回撤 {s['max_drawdown_fraction']:.2%}    成交 {s['fills']} 笔")
        self.mode.set('合成行情 · 演示参数 · 不代表真实表现' if s['synthetic_data'] else '导入行情 · 使用所选合约配置 · 结果仅供研究')
        self.table.delete(*self.table.get_children())
        for t in trades[:5000]:
            self.table.insert('', 'end', values=(t['timestamp'], {'open':'开仓','close':'平仓','close_today':'平今'}[t['action']], '买' if t['side'] > 0 else '卖', f"{t['price']:.2f}", f"{t['fee']:.2f}", f"{t['realized_pnl']:.2f}"))
        self.status.set(f'完成 · {len(curve):,} 根 K 线 · 成交表最多显示 5,000 笔，导出包含全部记录')
        self.export_btn.configure(state='normal')
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if not self.result or w < 160 or h < 100:
            c.create_text(max(w/2, 80), max(h/2, 50), text='运行回测后查看权益变化', fill='#8292a2')
            return
        curve = self.result[2]
        values = [self.result[0]['initial_capital']] + [p['equity'] for p in curve]
        lo, hi = min(values), max(values)
        pad = (hi - lo) * .1 or max(abs(hi) * .01, 1)
        lo, hi = lo-pad, hi+pad
        for i in range(5):
            y = 24 + (h-65) * i / 4
            c.create_line(90, y, w-24, y, fill='#e6edf2')
            c.create_text(80, y, text=f'{hi-(hi-lo)*i/4:,.0f}', anchor='e', fill='#627387')
        # Render an envelope for each pixel bucket to retain equity extremes.
        bucket = max(1, len(values)//max(int(w-114), 1))
        indices = {0, len(values)-1}
        for i in range(0, len(values), bucket):
            segment = range(i, min(i+bucket, len(values)))
            indices.update((min(segment, key=values.__getitem__), max(segment, key=values.__getitem__)))
        points = []
        for i in sorted(indices):
            points.extend((90+(w-114)*i/max(len(values)-1, 1), 24+(h-65)*(hi-values[i])/(hi-lo)))
        c.create_line(*points, fill='#138f96', width=2)
        c.create_text(90, h-20, text=curve[0]['timestamp'], anchor='w', fill='#627387')
        c.create_text(w-24, h-20, text=curve[-1]['timestamp'], anchor='e', fill='#627387')

    def export(self):
        if not self.result:
            return
        parent = filedialog.askdirectory(title='选择结果保存位置')
        if parent:
            try:
                folder = export_result(self.result, parent)
                self.status.set('已保存：' + str(folder))
                messagebox.showinfo('导出完成', str(folder))
            except OSError as exc:
                messagebox.showerror('导出失败', str(exc))


def smoke_test(marker):
    import tempfile
    app = App()
    app.update()
    result = run_research()
    app.show_result(result)
    app.update()
    assert app.table.get_children() and app.canvas.find_all()
    with tempfile.TemporaryDirectory() as tmp:
        folder = export_result(result, tmp)
        assert (folder / 'summary.json').exists()
        assert len(list(folder.iterdir())) == 3
        config = Path(tmp) / 'config.json'
        config.write_text(json.dumps(asdict(Config())), encoding='utf-8')
        bars = Path(tmp) / 'bars.csv'
        with bars.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(demo()[0]))
            writer.writeheader(); writer.writerows(demo())
        imported = run_research(str(bars), str(config))
        assert imported[0]['net_pnl'] == result[0]['net_pnl']
        assert not imported[0]['synthetic_data']
    app.destroy()
    Path(marker).write_text('desktop smoke test passed', encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        smoke_test(sys.argv[2])
    else:
        App().mainloop()
