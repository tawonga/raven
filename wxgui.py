__author__ = 'ray'
import os
import collections
import Queue
import wx
from wx.lib.stattext import GenStaticText
import datetime

import matplotlib
import matplotlib.dates
from matplotlib.ticker import FuncFormatter

import wx.lib.inspection

matplotlib.use('WXAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigCanvas


class PowerSensor(object):

    def __init__(self, plot_queue, msg_list_fifo, init=100):
        self.UNKNOWN = "unknown"
        self.PAD = " " * 30
        self.plot_queue = plot_queue
        self.msg_list_fifo = msg_list_fifo
        self.power_times = collections.deque(maxlen=init)
        self.power_values = collections.deque(maxlen=init)
        self.smartmeter_mac_address = self.UNKNOWN + self.PAD
        self.raven_mac_address = self.UNKNOWN
        self.smartmeter_channel = self.UNKNOWN + self.PAD
        self.smartmeter_signal = self.UNKNOWN + self.PAD

    def refresh(self):
        more_power_reads = True
        while more_power_reads:
            try:
                reading = self.plot_queue.get(block=False)
                if reading["type"] == "0":
                    self.smartmeter_mac_address = reading["smartmeter_mac_address"]
                    self.raven_mac_address = reading["raven_mac_address"]
                    self.power_times.append(reading["msg_time"])
                    self.power_values.append(reading["msg_value"])
                if reading["type"] == "3":
                    self.smartmeter_channel = reading["Channel"]
                    self.smartmeter_signal = reading["LinkStrength"]
                self.msg_list_fifo.append(reading)
            except Queue.Empty:
                more_power_reads = False

        return self.power_times, self.power_values

    
class InfoBox(object):

    def __init__(self, panel=None, label='', field_dfn=None, font=None):
        self.label = label
        self.field_dfn = field_dfn
        self.box = wx.StaticBox(panel, -1, label)
        self.box_sizer = wx.StaticBoxSizer(self.box, wx.VERTICAL)
        self.flex_sizer = wx.FlexGridSizer(rows=2,cols=2,hgap=8,vgap=8)
        for fld, seq in sorted(self.field_dfn.items(), key=lambda (k,v): v['seq']):
            spec = self.field_dfn[fld]
            tag = GenStaticText(panel, -1, label=fld+":")
            tag.SetFont(font)
            spec["display"] = GenStaticText(panel, -1, label=spec["value"])
            spec["display"].SetFont(font)
            self.flex_sizer.Add(tag, 0, wx.ALIGN_RIGHT)
            self.flex_sizer.Add(spec["display"], 0, wx.ALIGN_LEFT | wx.GROW)
        self.box_sizer.Add(self.flex_sizer, 0, flag=wx.ALIGN_LEFT | wx.TOP | wx.GROW)

    def set_field_value(self, tag, new_value):
        self.field_dfn[tag]["value"] = new_value
        self.field_dfn[tag]["display"].SetLabel(new_value)


class MessageList(wx.ListCtrl):

    def __init__(self, parent, msg_list_fifo):
        super(MessageList, self).__init__(parent, size=(400,100), style=wx.LC_REPORT)

        self.msg_list_fifo = msg_list_fifo

        self.InsertColumn(0, "timestamp", format=wx.LIST_FORMAT_LEFT)
        self.InsertColumn(1, "type", format=wx.LIST_FORMAT_CENTER)
        self.InsertColumn(2, "content", format=wx.LIST_FORMAT_LEFT)

        self.index = 0

    def format_message(self, msg):
        content_format = "channel: {} sig: {} desc: {}"
        formatted_msg = {"msg_time" : msg["msg_time"].strftime('%H:%M:%S'),
                         "type" : msg["type"]}
        if msg["type"] in ["0", "1"]:
            formatted_msg["content"] = "{:,} watts".format(msg["msg_value"])
        elif msg["type"] == "3":
            formatted_msg["content"] = content_format.format(msg["channel"], msg["link_strength"], msg["status"])
        return formatted_msg

    def push_message(self, msg):
        if self.index >= 99:
            self.DeleteItem(99)
        formatted_msg = self.format_message(msg)
        self.InsertStringItem(0, formatted_msg["msg_time"])
        self.SetStringItem(0, 1, formatted_msg["type"])
        self.SetStringItem(0, 2, formatted_msg["content"])
        self.SetColumnWidth(0, 80)
        self.SetColumnWidth(1, 40)
        self.SetColumnWidth(2, 280)
        self.index += 1

    def refresh(self):
        have_queued_messages = True
        while have_queued_messages:
            try:
                msg = self.msg_list_fifo.popleft()
                self.push_message(msg)
            except IndexError:
                have_queued_messages = False


class GraphFrame(wx.Frame):

    def __init__(self, plot_queue=None, stop_request=None, plot_pause_request=None, tracer=None, recorder=None):
        self.title = 'Smartmeter Monitor'
        self.stop_request = stop_request
        self.plot_pause_request = plot_pause_request
        self.plot_queue = plot_queue
        self.recorder = recorder
        self.tracer=tracer
        self.small_font = wx.Font(8, wx.DEFAULT, wx.NORMAL, wx.NORMAL, False)

        wx.Frame.__init__(self, None, -1, self.title)

        self.msg_list_fifo = collections.deque()

        self.power_sensor = PowerSensor(self.plot_queue, self.msg_list_fifo)
        self.power_sensor.refresh()
        self.paused = False

        self.create_menu_bar()
        self.create_status_bar()
        self.create_main_panel()

        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.redraw_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_redraw_timer, self.redraw_timer)
        self.redraw_timer.Start(3000)

    def menu_data(self):
        return (("&File",
                        ("&Save plot\tCtrl-S", "Save plot to file", self.on_save_plot),
                        ("E&xit\tCtrl-X",      "Exit",              self.on_exit)),
                 ("&Diagnostics",
                        ("&Widget Inspector", "Launch wxPython Widget Inspector", self.on_widget_inspector)))

    def create_menu_bar(self):
        menu_bar = wx.MenuBar()
        for each_menu_data in self.menu_data():
            label = each_menu_data[0]
            self.items = each_menu_data[1:]
            menu_bar.Append(self.create_menu(self.items), label)
        self.SetMenuBar(menu_bar)

    def create_menu(self, menu_data):
        menu = wx.Menu()
        for each_label, each_status, each_handler in menu_data:
            if not each_label:
                menu.AppendSeparator()
                continue
            menu_item = menu.Append(-1, each_label, each_status)
            self.Bind(wx.EVT_MENU, each_handler, menu_item)
        return menu

    def ravenTextFieldData(self):
        labels = [('port',1),
                  ('pid:vid',2),
                  ('description',3),
                  ('mac address', 4)]
        raven_data = {label: {"seq": seq, "value" :'', 'display' : ''} for label, seq in labels}
        raven_data["port"]["value"] = self.tracer.raven_config["port"]
        raven_data["pid:vid"]["value"] = self.tracer.raven_config["id"]
        raven_data["description"]["value"] = self.tracer.raven_config["desc"]
        raven_data["mac address"]["value"] = self.power_sensor.raven_mac_address
        return raven_data

    def smartmeterTextFieldData(self):
        labels = [('mac address', 1),
                  ('channel',2),
                  ('signal',3)]
        smartmeter_data = {label: {"seq": seq, "value" :'', 'display' : ''} for label, seq in labels}
        smartmeter_data["mac address"]["value"] = self.power_sensor.smartmeter_mac_address
        smartmeter_data["channel"]["value"] = self.power_sensor.smartmeter_channel
        smartmeter_data["signal"]["value"] = self.power_sensor.smartmeter_signal
        return smartmeter_data

    def create_main_panel(self):
        self.panel = wx.Panel(self)

        self.init_plot()
        self.canvas = FigCanvas(self.panel, -1, self.fig)

        self.pause_button = wx.Button(self.panel, -1, "Pause Monitoring")
        self.Bind(wx.EVT_BUTTON, self.on_pause_button, self.pause_button)
        self.Bind(wx.EVT_UPDATE_UI, self.on_update_pause_button, self.pause_button)

        self.raven_field_dfn = self.ravenTextFieldData()
        self.raven_box = InfoBox(self.panel, "RAVEn radio adapter", self.raven_field_dfn, font=self.small_font)

        self.smartmeter_field_dfn = self.smartmeterTextFieldData()
        self.smartmeter_box = InfoBox(self.panel, "smartmeter", self.smartmeter_field_dfn, font=self.small_font)

        self.msg_list = MessageList(self.panel, self.msg_list_fifo)
        self.msg_list.SetFont(self.small_font)

        self.hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox1.Add(self.pause_button, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)

        self.hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox2.Add(self.raven_box.box_sizer, border=5, flag=wx.ALL | wx.TOP)
        self.hbox2.Add(self.smartmeter_box.box_sizer, border=5, flag=wx.ALL | wx.TOP)
        self.hbox2.Add(self.msg_list, border=5, flag=wx.ALL | wx.TOP | wx.GROW)

        self.vbox = wx.BoxSizer(wx.VERTICAL)
        self.vbox.Add(self.canvas, 0, flag=wx.LEFT | wx.TOP | wx.GROW)
        self.vbox.Add(self.hbox1, 0, flag=wx.ALIGN_LEFT | wx.TOP | wx.GROW)
        self.vbox.Add(self.hbox2, 0, flag=wx.ALIGN_LEFT | wx.TOP | wx.GROW)

        self.panel.SetSizer(self.vbox)
        self.vbox.Fit(self)

    def create_status_bar(self):
        self.status_bar = self.CreateStatusBar()

    def scale_axes(self):
        now = datetime.datetime.now()
        ago = now - datetime.timedelta(seconds=800)
        x_max = matplotlib.dates.date2num(now)
        x_min = matplotlib.dates.date2num(ago)
        y_min = 0
        y_max = 5000 if len(self.power_sensor.power_values) < 1 else max(5000, max(self.power_sensor.power_values))
        return (x_min, x_max), (y_min, y_max)

    def init_plot(self):
        self.dpi = 100
        self.fig = Figure((9.0, 4.0), dpi=self.dpi)

        minutes = matplotlib.dates.MinuteLocator()
        minutesFmt = matplotlib.dates.DateFormatter('%H:%M')

        def thousands(self,x):
            return "{:,}".format(x)

        self.axes = self.fig.add_subplot(111)

        self.plot_data = self.axes.plot_date(x=list(self.power_sensor.power_times), xdate=True,
                                             y=list(self.power_sensor.power_values), ydate=False,
                                             fmt='-')[0]
        self.axes.set_axis_bgcolor('white')
        self.axes.set_title(self.title, size=12)
        self.axes.xaxis.set_major_locator(minutes)
        self.axes.xaxis.set_major_formatter(minutesFmt)
        self.axes.yaxis.set_major_formatter(FuncFormatter(thousands))
        self.axes.set_ylabel("kilowatts")
        (x_min, x_max), (y_min, y_max) = self.scale_axes()
        self.axes.set_xbound(lower=x_min, upper=x_max)
        self.axes.set_ybound(lower=0, upper=5000)


    def draw_plot(self):
        """ Redraws the plot
        """
        (x_min, x_max), (y_min, y_max) = self.scale_axes()
        self.axes.set_xbound(lower=x_min, upper=x_max)
        self.axes.set_ybound(lower=y_min, upper=y_max)

        self.axes.grid(True, color='gray')

        for tick in self.axes.xaxis.get_major_ticks():
            tick.label.set_fontsize(8)
            tick.label.set_rotation('vertical')

        for tick in self.axes.yaxis.get_major_ticks():
            tick.label.set_fontsize(10)

        self.plot_data.set_xdata(self.power_sensor.power_times)
        self.plot_data.set_ydata(self.power_sensor.power_values)

        self.canvas.draw()

    def on_pause_button(self, event):
        self.paused = not self.paused
        if self.paused:
            self.plot_pause_request.set()
        else:
            self.plot_pause_request.clear()

    def on_update_pause_button(self, event):
        label = "Resume Monitoring" if self.paused else "Pause Monitoring"
        self.pause_button.SetLabel(label)

    def on_save_plot(self, event):
        file_choices = "PNG (*.png)|*.png"

        dlg = wx.FileDialog(self,
                            message="Save plot as...",
                            defaultDir=os.getcwd(),
                            defaultFile="plot.png",
                            wildcard=file_choices,
                            style=wx.SAVE)

        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.canvas.print_figure(path, dpi=self.dpi)
            self.flash_status_message("Saved to %s" % path)

    def on_redraw_timer(self, event):
        # if paused do not add data, but still redraw the plot
        # (to respond to scale modifications, grid change, etc.)
        #
        if not self.paused:
            self.power_sensor.refresh()
        self.draw_plot()

        self.msg_list.refresh()

        self.raven_box.set_field_value('mac address', self.power_sensor.raven_mac_address)
        self.smartmeter_box.set_field_value('mac address', self.power_sensor.smartmeter_mac_address)
        self.smartmeter_box.set_field_value('channel', self.power_sensor.smartmeter_channel)
        self.smartmeter_box.set_field_value('signal', self.power_sensor.smartmeter_signal)

    def on_widget_inspector(self, event):
        wx.lib.inspection.InspectionTool().Show()

    def on_exit(self, event):
        self.stop_request.set()
        self.recorder.join()
        self.Destroy()

    def on_close(self, event):
        self.stop_request.set()
        self.recorder.join()
        self.Destroy()

    def flash_status_message(self, msg, flash_len_ms=1500):
        self.status_bar.SetStatusText(msg)
        self.timer_off = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_flash_status_off, self.timer_off)
        self.timer_off.Start(flash_len_ms, oneShot=True)

    def on_flash_status_off(self, event):
        self.status_bar.SetStatusText('')


class RavenApp(wx.App):

    def __init__(self, redirect=True, filename=None, useBestVisual=False, clearSigInt=True,
                 plot_queue=None, stop_request=None, plot_pause_request=None, tracer=None, recorder=None):
        self.plot_queue = plot_queue
        self.stop_request = stop_request
        self.plot_pause_request= plot_pause_request
        self.recorder = recorder
        self.tracer = tracer
        wx.App.__init__(self, redirect, filename, useBestVisual, clearSigInt)

    def OnInit(self):
        self.frame = GraphFrame(plot_queue=self.plot_queue,
                                stop_request=self.stop_request,
                                plot_pause_request=self.plot_pause_request,
                                tracer=self.tracer,
                                recorder = self.recorder)
        self.frame.Show(True)
        return True

    def OnExit(self):
        pass

