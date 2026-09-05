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
    for point, bar in zip(curve, bars):
        point.update({key: bar[key] for key in ('open','high','low','close')})
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
        self.title('云游客 · 期货研究台 0.4 | 离线回测')
        self.geometry('1460x900')
        self.minsize(1180, 780)
        self.configure(bg='#080f17')
        self.result = None
        self.mailbox = queue.Queue()
        self.csv_path = tk.StringVar()
        self.config_path = tk.StringVar()
        self.status = tk.StringVar(value='就绪 · 点击运行演示，或导入单一合约 CSV')
        self.metrics = tk.StringVar()
        self.mode = tk.StringVar(value='未载入行情 · 非实时数据')
        self.quote = tk.StringVar(value='—')
        self.data_info = tk.StringVar(value='暂无数据\n\n支持单一实际合约 CSV\n时间与交易日由数据源提供')
        self.signal_info = tk.StringVar(value='等待回测数据\n\n使用双均线规则\n并非 AI 实时信号')
        self.metric_values = [tk.StringVar(value='—') for _ in range(4)]
        self.chart_mode = tk.StringVar(value='candles')
        bg, panel, fg, muted = '#080f17', '#0e1924', '#dfe8f2', '#8494a5'
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI',10), background=panel, foreground=fg)
        style.configure('TFrame',background=panel)
        style.configure('TLabel',background=panel,foreground=fg)
        style.configure('TButton',padding=(10,9),background='#1a2b3b',foreground=fg,borderwidth=0)
        style.map('TButton',background=[('active','#28465d'),('disabled','#152332')],foreground=[('disabled','#596b7b')])
        style.configure('Primary.TButton',background='#1261db',foreground='white')
        style.map('Primary.TButton',background=[('active','#2879f0'),('disabled','#193552')])
        style.configure('TEntry',padding=7,fieldbackground='#142332',foreground=fg,insertcolor='white')
        style.configure('Treeview',rowheight=30,background=panel,fieldbackground=panel,foreground=fg,borderwidth=0,font=('Microsoft YaHei UI',9))
        style.configure('Treeview.Heading',background='#152330',foreground='#9aafc3',padding=7,font=('Microsoft YaHei UI',9))
        style.map('Treeview',background=[('selected','#1b405a')])
        style.configure('TNotebook',background=panel,borderwidth=0)
        style.configure('TNotebook.Tab',padding=(18,10),background=panel,foreground=muted)
        style.map('TNotebook.Tab',background=[('selected','#142839')],foreground=[('selected','#42a4ff')])
        style.configure('TRadiobutton',background=panel,foreground=fg)
        style.map('TRadiobutton',background=[('active',panel)])
        style.configure('Horizontal.TProgressbar',background='#208df0',troughcolor='#15212d',borderwidth=0)
        head=tk.Frame(self,bg=bg,padx=18,pady=14)
        head.pack(fill='x')
        tk.Label(head,text='◉ 云游客',bg=bg,fg='#72a7ff',font=('Microsoft YaHei UI',20,'bold')).pack(side='left')
        tk.Label(head,text='  QUANT DESK',bg=bg,fg=fg,font=('Segoe UI',15,'bold')).pack(side='left')
        tk.Label(head,text='离线研究版  v0.4',bg='#20324a',fg='#9abce7',padx=10,pady=4).pack(side='right')
        self.nav=[]
        for i,title in enumerate(['行情回测','成交记录','使用指南']):
            btn=tk.Button(head,text=title,bg=bg,fg=muted,bd=0,padx=18,pady=7,font=('Microsoft YaHei UI',11),command=lambda idx=i:self.tabs.select(idx))
            btn.pack(side='left',padx=(12 if i==0 else 0,0))
            self.nav.append(btn)
        body=tk.Frame(self,bg=bg)
        body.pack(fill='both',expand=True,padx=8,pady=(0,8))
        body.columnconfigure(1,weight=1)
        body.rowconfigure(0,weight=1)
        left=tk.Frame(body,bg=panel,width=235,padx=14,pady=14,highlightbackground='#1d2c39',highlightthickness=1)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        left.grid_propagate(False)
        # Side panels use pack internally; only their width is fixed.
        left.pack_propagate(False)
        def label(parent,text,size=10,color=fg):
            widget=tk.Label(parent,text=text,bg=panel,fg=color,font=('Microsoft YaHei UI',size),anchor='w',justify='left')
            widget.pack(fill='x',pady=(0,8))
            return widget
        label(left,'行情数据',13)
        label(left,'本地文件 / 单合约',9,muted)
        for title,var in [('行情 CSV',self.csv_path),('合约配置 JSON',self.config_path)]:
            label(left,title,10)
            ttk.Entry(left,textvariable=var).pack(fill='x',pady=(0,6))
            ttk.Button(left,text='选择文件',command=lambda v=var:self.pick(v)).pack(fill='x',pady=(0,14))
        ttk.Button(left,text='保存配置示例',command=self.save_config).pack(fill='x',pady=(0,18))
        tk.Frame(left,bg='#263745',height=1).pack(fill='x',pady=(0,14))
        tk.Label(left,textvariable=self.data_info,bg=panel,fg='#9cabb9',justify='left',anchor='nw',wraplength=202,font=('Microsoft YaHei UI',9)).pack(fill='x',pady=(0,20))
        label(left,'策略状态',13)
        tk.Label(left,textvariable=self.signal_info,bg='#112333',fg='#a7cddd',justify='left',anchor='nw',wraplength=182,padx=10,pady=12,font=('Microsoft YaHei UI',10)).pack(fill='x')
        tk.Label(left,text='AI 分析尚未接入\n不显示虚构评分或实时信号',bg=panel,fg=muted,justify='left',font=('Microsoft YaHei UI',9)).pack(side='bottom',anchor='w',pady=12)
        middle=ttk.Frame(body,padding=12)
        middle.grid(row=0,column=1,sticky='nsew')
        quote_row=ttk.Frame(middle)
        quote_row.pack(fill='x')
        ttk.Label(quote_row,text='行情 / 策略回测',font=('Microsoft YaHei UI',16,'bold')).pack(side='left')
        ttk.Label(quote_row,textvariable=self.quote,foreground='#ff5b62',font=('Segoe UI',20,'bold')).pack(side='right')
        ttk.Label(middle,textvariable=self.mode,foreground=muted,wraplength=600).pack(anchor='w',pady=(8,12))
        toolbar=ttk.Frame(middle)
        toolbar.pack(fill='x',pady=(0,8))
        for title,value in [('K 线 + 均线','candles'),('权益曲线','equity')]:
            ttk.Radiobutton(toolbar,text=title,variable=self.chart_mode,value=value,command=self.draw).pack(side='left',padx=(0,15))
        ttk.Label(toolbar,text='原始周期 · 最近 120 根 K 线',foreground=muted,font=('Microsoft YaHei UI',9)).pack(side='right')
        self.tabs=ttk.Notebook(middle)
        self.tabs.pack(fill='both',expand=True)
        chart_page=ttk.Frame(self.tabs)
        self.tabs.add(chart_page,text='行情回测')
        self.canvas=tk.Canvas(chart_page,bg=panel,highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<Motion>',self.chart_hover)
        self.canvas.bind('<Leave>',lambda e:self.canvas.delete('hover'))
        table_page=ttk.Frame(self.tabs)
        self.tabs.add(table_page,text='成交记录')
        cols=('timestamp','action','side','price','fee','realized_pnl')
        self.table=ttk.Treeview(table_page,columns=cols,show='headings')
        for col,title in zip(cols,['时间','开平','买卖','价格','手续费','盈亏 / 未扣费']):
            self.table.heading(col,text=title)
            self.table.column(col,width=155 if col=='timestamp' else 95,minwidth=70)
        self.table.tag_configure('even',background='#12202d')
        scroll=ttk.Scrollbar(table_page,command=self.table.yview)
        xscroll=ttk.Scrollbar(table_page,orient='horizontal',command=self.table.xview)
        self.table.configure(yscrollcommand=scroll.set,xscrollcommand=xscroll.set)
        scroll.pack(side='right',fill='y')
        xscroll.pack(side='bottom',fill='x')
        self.table.pack(fill='both',expand=True)
        help_page=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(help_page,text='使用指南')
        guide=tk.Text(help_page,wrap='word',bg=panel,fg=fg,relief='flat',font=('Microsoft YaHei UI',11),padx=10,pady=12)
        guide_scroll=ttk.Scrollbar(help_page,command=guide.yview)
        guide.configure(yscrollcommand=guide_scroll.set)
        guide_scroll.pack(side='right',fill='y')
        guide.pack(fill='both',expand=True)
        guide.insert('1.0','开始使用\n\n点击运行演示，无需账户或网络。演示价格为合成数据，并非当前市场行情。\n\n真实 CSV 字段：timestamp,trading_day,open,high,low,close。仅用单一实际合约；时间为无时区北京时间，交易日由数据源提供。\n\n保存配置示例后，按真实合约修改乘数、价位、保证金及费用。选择 CSV 和 JSON 后点击开始回测。\n\nK 线显示最近 120 根原始数据，MA 使用所选配置中的快慢窗口；权益曲线显示全部回测区间。悬停查看数值。没有成交量字段，因此不绘制成交量或买卖盘口。\n\n导出每次创建独立文件夹，包含汇总、成交、权益和 OHLC 记录。成交表最多显示 5,000 笔，导出包含全部。\n\n模型边界\n\n收盘产生信号、下一根开盘执行；止损和日亏损在收盘检查，末根收盘清仓。未模拟涨跌停排队、强平、结算价结算、换月和交易日历。止损不保证实际最大亏损。\n\n恒力期货接口尚未配置。AI 与实盘下单均未接入。')
        guide.configure(state='disabled')
        self.tabs.bind('<<NotebookTabChanged>>',lambda e:self.sync_nav())
        self.sync_nav()
        self.progress=ttk.Progressbar(middle,mode='indeterminate')
        self.progress.pack(fill='x',pady=(12,5))
        ttk.Label(middle,textvariable=self.status,foreground=muted,wraplength=600,font=('Microsoft YaHei UI',9)).pack(anchor='w')
        right=tk.Frame(body,bg=panel,width=248,padx=16,pady=14,highlightbackground='#1d2c39',highlightthickness=1)
        right.grid(row=0,column=2,sticky='nsew',padx=(8,0))
        right.pack_propagate(False)
        label(right,'回测控制',13)
        label(right,'双均线策略 · 每次一手',9,muted)
        self.demo_btn=ttk.Button(right,text='运行演示',command=lambda:self.start(True))
        self.demo_btn.pack(fill='x',pady=(4,10))
        self.run_btn=ttk.Button(right,text='开始回测',style='Primary.TButton',command=lambda:self.start(False))
        self.run_btn.pack(fill='x',pady=(0,10))
        self.export_btn=ttk.Button(right,text='导出结果',command=self.export,state='disabled')
        self.export_btn.pack(fill='x',pady=(0,20))
        label(right,'资金 / 回测指标',13)
        for i,title in enumerate(['期末权益 / 元','净收益 / 元','最大回撤','成交笔数']):
            card=tk.Frame(right,bg='#122230',padx=12,pady=9)
            card.pack(fill='x',pady=(0,7))
            tk.Label(card,text=title,bg='#122230',fg=muted,font=('Microsoft YaHei UI',9)).pack(anchor='w')
            tk.Label(card,textvariable=self.metric_values[i],bg='#122230',fg='#dcebf7',font=('Segoe UI',20,'bold')).pack(anchor='w')
        tk.Frame(right,bg='#263745',height=1).pack(fill='x',pady=10)
        label(right,'恒力期货 · 接入待配置',10,muted)
        ttk.Button(right,text='实盘下单未启用',state='disabled').pack(fill='x')
        self.after(100,self.poll)

    def sync_nav(self):
        selected=self.tabs.index(self.tabs.select())
        for i,button in enumerate(self.nav):
            button.configure(bg='#224159' if i==selected else '#13243a',fg='white' if i==selected else '#afc2d4')

    def chart_hover(self,event):
        if self.chart_mode.get() == 'candles':
            self.candle_hover(event)
            return
        c=self.canvas
        c.delete('hover')
        if not self.result or c.winfo_width()<160 or c.winfo_height()<100:
            return
        curve=self.result[2]
        fraction=max(0,min(1,(event.x-90)/max(c.winfo_width()-114,1)))
        index=round(fraction*len(curve))
        equity=self.result[0]['initial_capital'] if index==0 else curve[index-1]['equity']
        date='初始资金' if index==0 else curve[index-1]['timestamp']
        x=90+(c.winfo_width()-114)*index/len(curve)
        c.create_line(x,24,x,c.winfo_height()-41,fill='#8badb7',dash=(3,3),tags='hover')
        c.create_rectangle(94,2,c.winfo_width()-24,23,fill='#0e1924',outline='',tags='hover')
        c.create_text(100,12,text=f'{date}  |  权益 ¥{equity:,.2f}',anchor='w',fill='#087f8c',tags='hover')

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
        self.quote.set('—')
        self.signal_info.set('正在计算，等待结果…')
        self.data_info.set('加载所选数据…')
        self.metrics.set('正在计算…')
        for value in self.metric_values:
            value.set('—')
        self.progress.start(12)
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
            self.progress.stop()
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
        last=result[2][-1]
        self.quote.set(f"{last['close']:,.2f}")
        self.data_info.set(f"{'合成行情' if result[0]['synthetic_data'] else '导入行情'} · {len(result[2]):,} 根\n\n{result[2][0]['timestamp']}\n至 {last['timestamp']}")
        config=result[0]['config']
        closes=[r['close'] for r in result[2]]
        fast,slow=config['fast'],config['slow']
        signal='数据不足，等待更多 K 线'
        if len(closes)>=slow:
            delta=sum(closes[-fast:])/fast-sum(closes[-slow:])/slow
            signal='快线高于慢线' if delta>0 else ('快线低于慢线' if delta<0 else '快慢线相等')
        self.signal_info.set(f"MA {fast} / MA {slow}\n\n{signal}\n\n末根历史数据状态\n并非下单建议或 AI 信号")
        s, trades, curve = result
        for var, value in zip(self.metric_values,[f"{s['final_equity']:,.2f}", f"{s['net_pnl']:+,.2f}", f"{s['max_drawdown_fraction']:.2%}",str(s['fills'])]):
            var.set(value)
        self.metrics.set(f"期末权益 ¥{s['final_equity']:,.2f}    净收益 ¥{s['net_pnl']:,.2f}    最大回撤 {s['max_drawdown_fraction']:.2%}    成交 {s['fills']} 笔")
        self.mode.set('合成行情 · 演示参数 · 不代表真实表现' if s['synthetic_data'] else '导入行情 · 使用所选合约配置 · 结果仅供研究')
        self.table.delete(*self.table.get_children())
        for idx, t in enumerate(trades[:5000]):
            self.table.insert('', 'end', tags=('even',) if idx%2==0 else (), values=(t['timestamp'], {'open':'开仓','close':'平仓','close_today':'平今'}[t['action']], '买' if t['side'] > 0 else '卖', f"{t['price']:.2f}", f"{t['fee']:.2f}", f"{t['realized_pnl']:.2f}"))
        self.status.set(f'完成 · {len(curve):,} 根 K 线 · 成交表最多显示 5,000 笔，导出包含全部记录')
        self.export_btn.configure(state='normal')
        self.draw()

    def draw(self):
        if self.chart_mode.get() == 'candles':
            self.draw_candles()
            return
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
            c.create_line(90, y, w-24, y, fill='#20303e')
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
        c.create_line(*points, fill='#3fa9ec', width=2)
        c.create_text(90, h-20, text=curve[0]['timestamp'], anchor='w', fill='#627387')
        c.create_text(w-24, h-20, text=curve[-1]['timestamp'], anchor='e', fill='#627387')

    def draw_candles(self):
        c=self.canvas
        c.delete('all')
        w,h=c.winfo_width(),c.winfo_height()
        if not self.result or w<180 or h<180:
            c.create_text(max(90,w/2),max(90,h/2),text='加载行情后显示 K 线和均线',fill='#7e95a8')
            return
        all_rows=self.result[2]
        rows=all_rows[-120:]
        count=len(rows)
        left,right,top,bottom=16,w-72,48,h-40
        lo=min(row['low'] for row in rows)
        hi=max(row['high'] for row in rows)
        configs=self.result[0]['config']
        start=len(all_rows)-count
        averages=[]
        for window,color in [(configs['fast'],'#efbd45'),(configs['slow'],'#3ea8ef')]:
            # Rolling sums include history before the displayed window.
            values=[]
            rolling=0.0
            for j,row in enumerate(all_rows):
                rolling+=row['close']
                if j>=window:
                    rolling-=all_rows[j-window]['close']
                if j>=start and j+1>=window:
                    values.append((j-start,rolling/window))
            if values:
                lo=min(lo,min(v for _,v in values))
                hi=max(hi,max(v for _,v in values))
            averages.append((window,color,values))
        pad=(hi-lo)*.08 or 1
        lo,hi=lo-pad,hi+pad
        y=lambda price:top+(bottom-top)*(hi-price)/(hi-lo)
        step=(right-left)/count
        x=lambda index:left+step*(index+.5)
        for i in range(6):
            yy=top+(bottom-top)*i/5
            c.create_line(left,yy,right,yy,fill='#1f2d3b')
            c.create_text(right+8,yy,text=f'{hi-(hi-lo)*i/5:,.1f}',anchor='w',fill='#8599aa',font=('Segoe UI',9))
        for i,row in enumerate(rows):
            color='#ef5350' if row['close']>=row['open'] else '#22b879'
            xx=x(i)
            c.create_line(xx,y(row['high']),xx,y(row['low']),fill=color,tags='candle')
            a,b=sorted((y(row['open']),y(row['close'])))
            half=max(.7,step*.30)
            c.create_rectangle(xx-half,a,xx+half,max(a+1,b),fill=color,outline=color,tags='candle')
        offset=16
        for window,color,values in averages:
            points=[]
            for index,value in values:
                points.extend((x(index),y(value)))
            if len(points)>=4:
                c.create_line(*points,fill=color,width=1.5,tags='moving_average')
            c.create_text(offset,17,text=f'MA{window}',anchor='w',fill=color,font=('Segoe UI',10))
            offset+=86
        for i in sorted({0,count//2,count-1}):
            anchor='w' if i==0 else ('e' if i==count-1 else 'center')
            c.create_text(x(i),h-18,text=rows[i]['timestamp'][:10],anchor=anchor,fill='#8296a8',font=('Segoe UI',9))

    def candle_hover(self,event):
        c=self.canvas
        c.delete('hover')
        if not self.result or c.winfo_width()<180 or c.winfo_height()<180:
            return
        rows=self.result[2][-120:]
        step=(c.winfo_width()-88)/len(rows)
        index=max(0,min(len(rows)-1,int((event.x-16)/step)))
        row=rows[index]
        x=16+step*(index+.5)
        c.create_line(x,48,x,c.winfo_height()-40,fill='#8badb7',dash=(3,3),tags='hover')
        c.create_rectangle(12,26,c.winfo_width()-72,45,fill='#0e1924',outline='',tags='hover')
        c.create_text(16,35,text=f"{row['timestamp']}  O {row['open']:g} H {row['high']:g} L {row['low']:g} C {row['close']:g}",anchor='w',fill='#c8dce9',font=('Segoe UI',9),tags='hover')

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
    assert app.metric_values[3].get() == str(result[0]['fills'])
    app.tabs.select(1); app.update()
    assert app.tabs.index(app.tabs.select()) == 1
    app.tabs.select(0); app.update()
    from types import SimpleNamespace
    app.chart_hover(SimpleNamespace(x=200))
    assert app.canvas.find_withtag('hover')
    assert app.canvas.find_withtag('candle')
    assert app.canvas.find_withtag('moving_average')
    app.chart_mode.set('equity'); app.draw(); app.update()
    app.chart_hover(SimpleNamespace(x=200))
    assert app.canvas.find_withtag('hover')
    app.chart_mode.set('candles'); app.draw(); app.update()
    if os.environ.get('DESKTOP_SCREENSHOT'):
        from PIL import ImageGrab
        ImageGrab.grab().save(os.environ['DESKTOP_SCREENSHOT'])
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
