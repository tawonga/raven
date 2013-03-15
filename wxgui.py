__author__ = 'ray'
import os
import collections
import Queue
import wx
from wx.lib.stattext import GenStaticText
import datetime

import matplotlib
import matplotlib.dates

matplotlib.use('WXAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigCanvas


class PowerSensor(object):

    def __init__(self, plot_queue, init=100):
        self.plot_queue = plot_queue
        self.power_times = collections.deque(maxlen=init)
        self.power_values = collections.deque(maxlen=init)
        self.smartmeter_mac_address = "unknown"
        self.raven_mac_address = "unknown"

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
            except Queue.Empty:
                more_power_reads = False

        return self.power_times, self.power_values


class GraphFrame(wx.Frame):

    def __init__(self, plot_queue=None, stop_request=None, plot_pause_request=None, tracer=None, recorder=None):
        self.title = 'Smart Meter Analyzer'
        self.stop_request = stop_request
        self.plot_pause_request = plot_pause_request
        self.plot_queue = plot_queue
        self.recorder = recorder
        self.tracer=tracer

        wx.Frame.__init__(self, None, -1, self.title)

        self.power_sensor = PowerSensor(self.plot_queue)
        self.power_sensor.refresh()
        self.paused = False

        self.create_menu()
        self.create_status_bar()
        self.create_main_panel()

        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.redraw_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_redraw_timer, self.redraw_timer)
        self.redraw_timer.Start(3000)

    def create_menu(self):
        self.menu_bar = wx.MenuBar()
        menu_file = wx.Menu()

        m_expt = menu_file.Append(-1, "&Save plot\tCtrl-S", "Save plot to file")
        self.Bind(wx.EVT_MENU, self.on_save_plot, m_expt)
        menu_file.AppendSeparator()
        m_exit = menu_file.Append(-1, "E&xit\tCtrl-X", "Exit")
        self.Bind(wx.EVT_MENU, self.on_exit, m_exit)
        self.menu_bar.Append(menu_file, "&File")
        self.SetMenuBar(self.menu_bar)

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

    def create_raven_info_panel(self):
        box = wx.StaticBox(self.panel, -1, "RAVEn Radio Adapter" )
        box_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        flex_sizer = wx.FlexGridSizer(rows=2,cols=2,hgap=8,vgap=8)
        small_font = wx.Font(8, wx.DEFAULT, wx.NORMAL, wx.NORMAL, False)
        self.raven_data = self.ravenTextFieldData()
        for fld, seq in sorted(self.raven_data.items(), key=lambda (k,v): v['seq']):
            spec = self.raven_data[fld]
            tag = GenStaticText(self.panel, -1, label=fld+":")
            tag.SetFont(small_font)
            spec["display"] = GenStaticText(self.panel, -1, label=spec["value"])
            spec["display"].SetFont(small_font)
            flex_sizer.Add(tag, 0, wx.ALIGN_RIGHT)
            flex_sizer.Add(spec["display"], 0, wx.ALIGN_LEFT | wx.GROW)
        self.Fit()
        box_sizer.Add(flex_sizer, 0, flag=wx.ALIGN_LEFT | wx.TOP | wx.GROW)
        return box_sizer
        
    def smartmeterTextFieldData(self):
        labels = [('mac address', 1),
                  ('channel',2),
                  ('signal',3)]
        smartmeter_data = {label: {"seq": seq, "value" :'', 'display' : ''} for label, seq in labels}
        smartmeter_data["mac address"]["value"] = self.power_sensor.smartmeter_mac_address
        return smartmeter_data

    def create_smartmeter_info_panel(self):
        smartmeter_box = wx.FlexGridSizer(rows=2,cols=2,hgap=8,vgap=8)
        small_font = wx.Font(8, wx.DEFAULT, wx.NORMAL, wx.NORMAL, False)
        self.smartmeter_data = self.smartmeterTextFieldData()
        for fld, seq in sorted(self.smartmeter_data.items(), key=lambda (k,v): v['seq']):
            spec = self.smartmeter_data[fld]
            tag = GenStaticText(self.panel, -1, label=fld + ":")
            tag.SetFont(small_font)
            spec["display"] = GenStaticText(self.panel, -1, label=spec["value"])
            spec["display"].SetFont(small_font)
            smartmeter_box.Add(tag, 0, wx.ALIGN_RIGHT)
            smartmeter_box.Add(spec["display"], 0, wx.ALIGN_LEFT | wx.GROW)
        self.Fit()
        return smartmeter_box

    def create_main_panel(self):
        self.panel = wx.Panel(self)

        self.init_plot()
        self.canvas = FigCanvas(self.panel, -1, self.fig)

        self.pause_button = wx.Button(self.panel, -1, "Pause")
        self.Bind(wx.EVT_BUTTON, self.on_pause_button, self.pause_button)
        self.Bind(wx.EVT_UPDATE_UI, self.on_update_pause_button, self.pause_button)

        self.raven_box = self.create_raven_info_panel()
        self.smartmeter_box = self.create_smartmeter_info_panel()

        self.hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox1.Add(self.pause_button, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)

        self.hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox2.Add(self.raven_box, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self.hbox2.Add(self.smartmeter_box, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)

        self.vbox = wx.BoxSizer(wx.VERTICAL)
        self.vbox.Add(self.canvas, 1, flag=wx.LEFT | wx.TOP | wx.GROW)
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

        self.axes = self.fig.add_subplot(111)
        self.plot_data = self.axes.plot_date(x=list(self.power_sensor.power_times), xdate=True,
                                             y=list(self.power_sensor.power_values), ydate=False,
                                             fmt='-')[0]
        self.axes.set_axis_bgcolor('black')
        self.axes.set_title(self.title, size=12)
        self.axes.xaxis.set_major_locator(minutes)
        self.axes.xaxis.set_major_formatter(minutesFmt)
        (x_min, x_max), (y_min, y_max) = self.scale_axes()
        self.axes.set_xbound(lower=x_min, upper=x_max)
        self.axes.set_ybound(lower=0, upper=5000)

    def draw_plot(self):
        """ Redraws the plot
        """
        (x_min, x_max), (y_min, y_max) = self.scale_axes()
        self.axes.set_xbound(lower=x_min, upper=x_max)
        self.axes.set_ybound(lower=y_min, upper=y_max)

        # anecdote: axes.grid assumes b=True if any other flag is
        # given even if b is set to False.
        # so just passing the flag into the first statement won't
        # work.
        #
        self.axes.grid(True, color='gray')

        # Using setp here is convenient, because get_xticklabels
        # returns a list over which one needs to explicitly
        # iterate, and setp already handles this.
        #
#        pylab.setp(self.axes.get_xticklabels(), visible=True)

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
        label = "Resume" if self.paused else "Pause"
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
        self.raven_data['mac address']["display"].SetLabel(self.power_sensor.raven_mac_address)
        self.smartmeter_data['mac address']["display"].SetLabel(self.power_sensor.smartmeter_mac_address)

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

