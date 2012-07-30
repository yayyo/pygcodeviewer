#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simple G-Code viewer

Dependencies:
wxPython (a Python wrapper for the wxWidgets platform GUI library)
NB method naming conventions (initial capital) used here are cf wxPython

wxPython Home http://wxpython.org/
wxPython API reference: http://wxpython.org/docs/api/

"""
import wx
from string import *
from math import *
import os
import sys
import locale
import re

# Globals
gUNIT = 1 # TODO: implement millimeters/Inches
gGCODES = []
gPATTERNS = []
gMouseLeftDown  = [0]*3
gMouseRightDown = [0]*3

gRotation_Angle = 0
gSHIFT_X = 0
gSHIFT_Y = 0
# Window
class MainFrame(wx.Frame):

	_paint = None # the panel used for drawing

	def __init__(self, parent, id, title):
		wx.Frame.__init__(self, parent, id, title, size=(800, 600))

		# Set up the menu
		filemenu= wx.Menu()
		menuOpen = filemenu.Append(wx.ID_OPEN,"&Open"," Open files")
		menuReload = filemenu.Append(wx.ID_REVERT,"&Reload"," Reload files")
		menuExit = filemenu.Append(wx.ID_EXIT,"E&xit"," Terminate the program")

		# Create the menubar
		menuBar = wx.MenuBar()
		menuBar.Append(filemenu,"&File")
		self.SetMenuBar(menuBar)

		# Menu bar events
		self.Bind(wx.EVT_MENU, self.OnOpen, menuOpen)
		self.Bind(wx.EVT_MENU, self.OnReload, menuReload)
		self.Bind(wx.EVT_MENU, self.OnExit, menuExit)

		panel = wx.Panel(self, -1)
		vbox = wx.BoxSizer(wx.VERTICAL)

		# Display set
		panel1 = wx.Panel(panel, -1)

		# Draw data
		panel2 = wx.Panel(panel, -1)
		hbox1 = wx.BoxSizer(wx.HORIZONTAL)

		self._paint = Paint(panel2)

		# View point radio buttons after PAINT instantiation
		vbox_view = wx.BoxSizer(wx.VERTICAL)
		radioList = ['XY', 'XZ', 'YZ', 'XYZ']
		rb1 = wx.RadioBox(panel1, label="View plane", choices=radioList, majorDimension=4, style=wx.RA_SPECIFY_COLS)
		rb1.SetSelection( self._paint.view_point )
		vbox_view.Add(rb1, 0, wx.BOTTOM | wx.TOP, 9)

		panel1.SetSizer(vbox_view)
		vbox.Add(panel1, 0, wx.BOTTOM | wx.TOP, 9)

		hbox1.Add(self._paint, 1, wx.EXPAND | wx.ALL, 2)
		panel2.SetSizer(hbox1)
		vbox.Add(panel2, 1,	 wx.LEFT | wx.RIGHT | wx.EXPAND, 2)

		hbox5 = wx.BoxSizer(wx.HORIZONTAL)
		btn2 = wx.Button(panel, -1, 'Close', size=(70, 30))
		hbox5.Add(btn2, 0, wx.LEFT | wx.BOTTOM , 5)
		vbox.Add(hbox5, 0, wx.ALIGN_RIGHT | wx.RIGHT, 10)

		panel.SetSizer(vbox)

		# Events
		self.Bind(wx.EVT_BUTTON, self.OnExit, btn2)
		self.Bind(wx.EVT_RADIOBOX, self.EvtRadioBox1, rb1)

		self.Centre()
		self.Show(True)

	# Functions
	def EvtRadioBox1(self,e):
		self._paint.view_point = e.GetInt()
		self.Refresh(True)

	def OnExit(self,e):
		self.Close(True)  # Close the frame.

	def OnOpen(self,e):
		setup = OpenFiles(None, -1, 'Open Files')
		setup.Destroy()
		self.Refresh(True)

	def OnReload(self,e):
		parseGCodeFile()
		
		
class Paint(wx.ScrolledWindow):
	"""
	Paint draws the G-Code path
	
	Scroll wheel event code is taken from Doug Anderson's 2006 post in Manning Forums:
	http://www.manning-sandbox.com/thread.jspa?threadID=19478

	Implements a version of wx.ScrolledWindow that is slightly saner.
	
	The major differences between this version of ScrolledWindow and the
	one that ships with wxPython:
	- It captures scrollwheel events from children.	 At the moment, it's not
	  very efficient at it, but it'll do.
	
	Since some of the workarounds implemented in this class are a bit hacky,
	I'd expect some amount of revisiting for future versions of wxPython
	and future platforms.
	
	Overall, mousewheel events seem to be all sorts of craziness on the two
	platforms I've tested (Mac and PC):
	- On Mac, they are sent to the control that the mouse is over.	On Windows,
	  they are sent to whatever has focus in the topmost frame.
	- On Mac, they aren't passed up the container heirarchy.  On Windows, they
	  are passed up the container heirarchy if not skipped (though not through
	  the standard 'propagation' method that command events are).  On Mac, this
	  means that if the mouse happens to be over a static label, the scroll
	  wheel won't do anything.
	- On Mac, you will get two scroll events, unless you don't skip the first
	  one.	They are different events: if the first event causes the mouse to
	  be over a different object, the new object will be the 'eventobject' of
	  the second event.
	- Horizontal scroll wheel events end up causing vertical scrolling.
	- On a PC, a multiline text control will 'skip' on mousewheel events (so
	  the app will get a chance to see them), then won't actually scroll if the
	  app eats them.  On a Mac, a multiline text control will 'skip' on
	  mousewheel events (again, app can see them), but will still scroll even
	  if the app eats them.
	
	Another attempted implementation of this class involved creating one big
	translucent window at the highest z-ordering.  This got all mousewheel
	events, but also stole all other mouse events (clicks, etc).  I couldn't
	find a way to get them passed down properly, thus that method wasn't used.
	
	""" 
	_center = None
	_centerX = 0.0
	_centerY = 0.0
	_centerZ = 0.0

	_shiftX = 0.0
	_shiftY = 0.0
	_shiftZ = 0.0
	
	_mag = 2.0
	_mag_MIN = 0.1
	_mag_MAX = 500.0
	
	# minimum/maximum coordinate values
	_minX = 0.0
	_maxX = 0.0
	_minY = 0.0
	_maxY = 0.0
	_minZ = 0.0
	_maxZ = 0.0

	_scale = 1.0
	_scale_min = 0.1
	_scale_max = 500.0
	_view_point = 0
	
	_move_colour = 'BLUE' # G-code moves colour

	# True for debugging messages (in the scroll wheel handling method)
	_debug = False
	#_debug = True

	def __init__(self, parent):
	
		wx.ScrolledWindow.__init__(self, parent,-1,style=wx.HSCROLL|wx.VSCROLL)
		self.SetBackgroundColour('WHITE')

		self._maxX = 0.0
		self._minX = 0.0
		self._maxY = 0.0
		self._minY = 0.0
		self._maxZ = 0.0
		self._minZ = 0.0		

		self.SetScrollbars(10, 10, 100, 100);

		self.Bind(wx.EVT_PAINT, self.OnPaint)		
		self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
		self.Bind(wx.EVT_PAINT, self.OnPaint)

		# http://www.manning-sandbox.com/thread.jspa?threadID=19478
		# Bind mousewheel handler to _app_, which is the only way we'll have
		# a chance to see mousewheel events of our children (and then, only if
		# they weren't handled).  ..._processingEvents is used to avoid
		# recursion in the handler.
		self._processingEvents = False
		wx.GetApp().Bind(wx.EVT_MOUSEWHEEL, self.OnAppMouseWheel)
		self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
		
		self.Bind(wx.EVT_LIST_BEGIN_DRAG, self.OnDrag)
		self.Bind(wx.EVT_LEFT_DOWN, self.OnMouseLeftDown)
		self.Bind(wx.EVT_RIGHT_DOWN, self.OnMouseRightDown)
		#self.Bind(wx.EVT_LEFT_DCLICK , self.OnMouseLeftDClick)
		#self.Bind(wx.EVT_RIGHT_DCLICK , self.OnMouseRightDClick)
		self.Bind(wx.EVT_LEFT_UP, self.OnMouseLeftUp)
		self.Bind(wx.EVT_RIGHT_UP, self.OnMouseRightUp)
		self.Bind(wx.EVT_MOTION , self.OnMouseMove) 

		self._shiftX =int( self.GetSize().x / 2 )
		self._shiftY =int( self.GetSize().y / 2 )

		self.Centre()
		self.Show(True)

	@property
	def maxX(self): return self._maxX

	@property
	def maxY(self): return self._maxY

	@property
	def maxZ(self): return self._maxZ

	@property
	def minX(self): return self._minX

	@property
	def minY(self): return self._minY

	@property
	def minZ(self): return self._minZ

	@property
	def mag(self):
		"""Get the current magnification factor."""
		return self._mag

	@mag.setter
	def mag(self, value=None):
		"""Set the magnification factor."""
		self._mag = value
		
	@property
	def view_point(self):
		"""Get the current point of view."""
		return self._view_point

	@view_point.setter
	def view_point(self, value=None):
		"""Set the point of view."""
		self._view_point = value

	def OnAppMouseWheel(self, event):
		"""
		Watch all app mousewheel events, looking for ones from descendants.
		If we see a mousewheel event that was unhandled by one of our
		descendants, we'll take it upon ourselves to handle it.
		
		@param	event  The mouse wheel event.
		
		"""
		# By default, we won't eat events...
		wantSkip = True
		
		# Avoid recursion--this function will get called during 'ProcessEvent'.
		if not self._processingEvents:
			if self._debug: print "Mousewheel event received at app level"
			
			self._processingEvents = True
			
			# Check who the event is targetting
			evtObject = event.GetEventObject()
			if self._debug:
				print "...targetting '%s'" % evtObject.GetLabel()
			
			# We only care about passing up events that were aimed at our
			# descendants, not us, so only search if it wasn't aimed at us.
			if evtObject != self:
				toTest = evtObject.GetParent()
				while toTest:
					if toTest == self:
						if self._debug: print "...detected that we are ancestor"
						
						# We are the "EventObject"'s ancestor, so we'll take
						# the event and pass it to our event handler.  Note:
						# we don't change the coordinates or evtObject.
						# Technically, we should, but our event handler doesn't
						# seem to mind.
						self.GetEventHandler().ProcessEvent(event)
						
						# We will _not_ skip here.
						wantSkip = False
						break
					toTest = toTest.GetParent()
					
			self._processingEvents = False

		elif self._debug:
			print "...recursive mousewheel event"
		
		# Usually, we skip the event and let others handle it, unless it's a
		# mouse event from our descendant...
		if wantSkip:
			event.Skip()

	def OnKeyDown(self, event):
		keycode = event.GetKeyCode()
		#print keycode
		#if keycode == wx.WXK_UP:

	def OnPaint(self, e):
		"""
		Draw the Gerber G-Code path
		
		"""
		global gPATTERNS

		dc = wx.PaintDC(self) # graphics device context

		view_offset = self.CalcUnscrolledPosition(0,0) # translate scrolled and unscrolled

		if ( len(gPATTERNS ) > 0):
			# update coordinates minima/maxima
			# for now we get rid of the global MIN/MAX variables this way			
			for patterns in gPATTERNS:
				for pattern in patterns.patterns:
					for point in pattern.points:
						if (point.x > self._maxX): self._maxX = point.x
						if (point.x < self._minX): self._minX = point.x
						if (point.y > self._maxY): self._maxY = point.y
						if (point.y < self._minY): self._minY = point.y
						if (point.z > self._maxZ): self._maxZ = point.z
						if (point.z < self._minZ): self._minZ = point.z
		
		self._center = POINT( 
		int( self.GetSize().x / 2 ) + (self.minX+self.maxX) / 2, 
		int( self.GetSize().y / 2 ) + (self.minY+self.maxY) / 2, 
		(self.minZ+self.maxZ) / 2 )

		if self._debug:
			dc.DrawRectangle( self._center.x-45*self._scale, self._center.y-30*self._scale, 90*self._scale, 60*self._scale)
				
		if ( len(gPATTERNS ) > 0):

			self.DrawAxis( dc )

			# draw the G-code path points
			for patterns in gPATTERNS:
				for pattern in patterns.patterns:
				
					if (self._view_point==0):	#XY
						p1x = pattern.points[0].x
						p1y = pattern.points[0].y
						p2x = pattern.points[1].x
						p2y = pattern.points[1].y
						
					elif (self._view_point==1):	#XZ
						p1x = pattern.points[0].x
						p1y = pattern.points[0].z
						p2x = pattern.points[1].x
						p2y = pattern.points[1].z
						
					elif (self._view_point==2):	#YZ
						p1x = pattern.points[0].y
						p1y = pattern.points[0].z
						p2x = pattern.points[1].y
						p2y = pattern.points[1].z
						
					else:	#XYZ
						p1,p2 = change_view(pattern.points[0], pattern.points[1])
						p1x = p1.x
						p1y = p1.y
						p2x = p2.x
						p2y = p2.y
						
					x1 =  p1x * self._scale + self._center.x - view_offset[0]
					y1 = -p1y * self._scale + self._center.y - view_offset[1]
					x2 =  p2x * self._scale + self._center.x - view_offset[0]
					y2 = -p2y * self._scale + self._center.y - view_offset[1]

					if (pattern.style == 0):	# rapid move
						dc.SetPen(wx.Pen(self._move_colour, 1, wx.DOT_DASH))
						dc.DrawLines(([x1,y1],[x2,y2]))

					if (pattern.style == 1):    # coordinated move
						dc.SetPen(wx.Pen(patterns.colour, 1, wx.SOLID))
						dc.DrawLines([[x1,y1],[x2,y2]])

					if (pattern.style == 2 or pattern.style == 3):  # coordinated helical move
						dc.SetPen(wx.Pen(patterns.colour, 1, wx.SOLID))
						dc.DrawArcPoint(pattern.p1,pattern.p2,pattern.center)
		
	def DrawAxis(self, dc):
		"""Draw the cartesian coordinate axis."""		
		view_offset = self.CalcUnscrolledPosition(0,0) # translate scrolled and unscrolled
		center = self._center

		axisLength = 45.0
		origin = POINT(self._center.x - view_offset[0], self._center.y - view_offset[1], self._center.z)

		dc.SetPen(wx.Pen('BLACK', 2, wx.SOLID)) # penwidth 2

		if (self._view_point==0):	#XY
			dc.DrawLines( ([origin.x,origin.y], [origin.x+axisLength,origin.y]) )	#X axis
			dc.DrawLines( ([origin.x,origin.y], [origin.x,origin.y-axisLength]) )	#Y axis
			
		elif (self._view_point==1): #XZ
			dc.DrawLines( ([origin.x,origin.y], [origin.x+axisLength,origin.y]) )	#X axis
			dc.DrawLines( ([origin.x,origin.y], [origin.x,origin.y-axisLength]) )	#Z axis
			
		elif (self._view_point==2): #YZ
			dc.DrawLines( ([origin.x,origin.y], [origin.x+axisLength,origin.y]) )	#Y axis
			dc.DrawLines( ([origin.x,origin.y], [origin.x,origin.y-axisLength]) )	#Z axis
			
		else: #XYZ
			co1,co2 = change_view( POINT(0.0,0.0,0.0), POINT(axisLength, 0.0, 0.0) )
			x1 =  co1.x+self._center.x - view_offset[0]
			y1 = -co1.y+self._center.y - view_offset[1]
			point1 = [x1, y1]
			x2 =  co2.x+self._center.x - view_offset[0]
			y2 = -co2.y+self._center.y - view_offset[1]
			point2 = [x2, y2]
			dc.DrawLines((point1,point2))	#X axis
			
			co1,co2 = change_view( POINT(0.0,0.0,0.0), POINT(0.0, axisLength, 0.0) )
			x1 =  co1.x+self._center.x - view_offset[0]
			y1 = -co1.y+self._center.y - view_offset[1]
			point1 = [x1, y1]
			x2 =  co2.x+self._center.x - view_offset[0]
			y2 = -co2.y+self._center.y - view_offset[1]
			point2 = [x2, y2]
			dc.DrawLines((point1,point2))	#Y axis
			
			dc.DrawLines( ([origin.x,origin.y], [origin.x,origin.y-axisLength]) )	#Z axis

	def zoom(self,x,y,z,factor):
		self._scale = factor * self._scale
		if self._scale < self._scale_min:
			self._scale = self._scale_min
		if self._scale > self._scale_max:
			self._scale = self._scale_max
		
		self._shiftX = x - (x-self._shiftX) * factor
		self._shiftY = y - (y-self._shiftY) * factor
		self._shiftZ = z - (z-self._shiftZ) * factor
		
		#penwidth = max(1.0,self.filament_width*((self.scale[0]+self.scale[1])/2.0))
		#for pen in self.penslist:
		#	pen.SetWidth(penwidth)
		self.Refresh(True)
        
	def OnMouseWheel(self, e):
		"""The mousewheel makes the image Zoom in, or out."""
		w=e.GetWheelRotation()
		if w > 0:
			self.zoom(e.GetX(), e.GetY(), 0, 1.2)
		elif w < 0:
			self.zoom(e.GetX(), e.GetY(), 0, 1/1.2)			
		self.Refresh(True)
		
	def OnDrag(self, event):
		pos = event.GetPosition()
		print "Drag: pos=" + str(pos)
		#self.Refresh(True)
		
	def OnMouseLeftDown(self, event):

		global gMouseLeftDown

		pos = event.GetPosition()
		gMouseLeftDown[0] = 1
		gMouseLeftDown[1] = pos.x
		gMouseLeftDown[2] = pos.y
		#print "Left Down: pos=" + str(pos)
		
	def OnMouseRightDown(self, event):

		global gMouseRightDown

		pos = event.GetPosition()
		gMouseRightDown[0] = 1
		gMouseRightDown[1] = pos.x
		gMouseRightDown[2] = pos.y
		#print "Right Down: pos=" + str(pos)
		
	def OnMouseLeftUp(self, event):

		global gMouseLeftDown

		pos = event.GetPosition()
		size = self.GetSize()
		if gMouseLeftDown[0]:
			gMouseLeftDown[0] = 0
			pre_mag = self._mag
			dx = pos.x - gMouseLeftDown[1]
			dy = pos.y - gMouseLeftDown[2]
			cx = pos.x - dx/2
			cy = pos.y - dy/2
			if (dx > 0):
				self._mag = float(size.x)/float(dx/pre_mag)
			elif (dx < 0):
				self._mag = -float(pre_mag)/float(dx)
			#print "self._mag=" + str(self._mag)
			if (dy > 0):
				if (self._mag > float(size.y)/float(dy/pre_mag)):
					self._mag = float(size.y)/float(dy/pre_mag)
			
			self._shiftX = float(self._centerX) - (self._mag*(float(cx)-self._shiftX))/pre_mag
			self._shiftY = float(self._centerY) - (self._mag*(float(cy)-self._shiftY))/pre_mag
			if (self._mag < self._mag_MIN):
				self._mag = self._mag_MIN
				self._shiftX = self._centerX
				self._shiftY = self._centerY
			if (self._mag > self._mag_MAX):
				self._mag = self._mag_MAX
				self._shiftX = float(self._centerX) - (self._mag*(float(cx)-self._shiftX))/pre_mag
				self._shiftY = float(self._centerY) - (self._mag*(float(cy)-self._shiftY))/pre_mag

			self.Refresh(True)

	def OnMouseRightUp(self, event):

		global gMouseRightDown

		pos = event.GetPosition()
		if gMouseRightDown[0]:
			gMouseRightDown[0] = 0
			dx = pos.x - gMouseRightDown[1]
			dy = pos.y - gMouseRightDown[2]
			dist = sqrt(dx*dx + dy*dy)/self._mag
			print dist
			
	def OnMouseLeftDClick(self, event):
		pos = event.GetPosition()
		
	def OnMouseRightDClick(self, event):
		pos = event.GetPosition()
		
	def OnMouseMove(self, event):
		pos = event.GetPosition()


class OpenFiles(wx.Dialog):
	"""
	Show a modal dialogue to select a G-code files and parses the file selected.
	
	"""
	_inch_flag = 0
	_gcode_ext = '*.ngc'
	_default_colour = 'CADET BLUE' # Cadet blue

	_colours = [
	'AQUAMARINE','BLACK','BLUE','BLUE VIOLET','BROWN',
	'CADET BLUE','CORAL','CORNFLOWER BLUE','CYAN','DARK GREY',
	'DARK GREEN', 'DARK OLIVE GREEN', 'DARK ORCHID', 'DARK SLATE BLUE', 'DARK SLATE GREY',
	'DARK TURQUOISE', 'DIM GREY', 'FIREBRICK', 'FOREST GREEN', 'GOLD',
	'GOLDENROD', 'GREY', 'GREEN', 'GREEN YELLOW', 'INDIAN RED',
	'KHAKI', 'LIGHT BLUE', 'LIGHT GREY', 'LIGHT STEEL BLUE', 'LIME GREEN',
	'MAGENTA', 'MAROON', 'MEDIUM AQUAMARINE', 'MEDIUM BLUE', 'MEDIUM FOREST GREEN',
	'MEDIUM GOLDENROD', 'MEDIUM ORCHID', 'MEDIUM SEA GREEN', 'MEDIUM SLATE BLUE', 'MEDIUM SPRING GREEN',
	'MEDIUM TURQUOISE', 'MEDIUM VIOLET RED', 'MIDNIGHT BLUE', 'NAVY', 'ORANGE',
	'ORANGE RED', 'ORCHID', 'PALE GREEN', 'PINK', 'PLUM',
	'PURPLE', 'RED', 'SALMON', 'SEA GREEN', 'SIENNA',
	'SKY BLUE', 'SLATE BLUE', 'SPRING GREEN', 'STEEL BLUE', 'TAN',
	'THISTLE ', 'TURQUOISE', 'VIOLET', 'VIOLET RED', 'WHEAT',
	'WHITE', 'YELLOW', 'YELLOW GREEN'
	]

	# True for debugging
	_debug = False
	#_debug = True

	def __init__(self, parent, id, title):
		wx.Dialog.__init__(self, parent, id, title, size=(250, 210))
		self.dirname=''

		panel = wx.Panel(self, -1)
		sizer = wx.GridBagSizer(0, 0)

		text1 = wx.StaticText(panel, -1, 'G-code file')
		sizer.Add(text1, (0, 0), flag= wx.LEFT | wx.TOP, border=10)

		self.gcode = wx.TextCtrl(panel, -1) # G-code filename
		sizer.Add(self.gcode, (0, 1), (1, 3), wx.TOP | wx.EXPAND, 5)

		button1 = wx.Button(panel, -1, 'Browse...', size=(-1, 30))
		sizer.Add(button1, (0, 4), (1, 1), wx.TOP | wx.LEFT | wx.RIGHT , 5)

		text2 = wx.StaticText(panel, -1, 'G-code colour')
		sizer.Add(text2, (1, 0), flag= wx.LEFT | wx.TOP, border=10)
		self.gcode_colour = wx.ComboBox(panel, -1, choices=self._colours, style=wx.CB_READONLY)
		self.gcode_colour.SetValue(str(self._default_colour))
		sizer.Add(self.gcode_colour, (1, 1), (1, 3), wx.TOP | wx.EXPAND, 5)

		radioList = ['mm', 'inch']
		rb1 = wx.RadioBox(panel, label="unit of Input file", choices=radioList, majorDimension=3, style=wx.RA_SPECIFY_COLS)
		rb1.SetSelection( int(self._inch_flag) )
		sizer.Add(rb1, (2, 0), (1, 5), wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT , 10)

		rot_ang_txt = wx.StaticText(panel, -1, 'Rotation angle (deg)')
		sizer.Add(rot_ang_txt, (3, 0), flag= wx.LEFT | wx.TOP, border=10)
		self.rot_ang = wx.TextCtrl(panel, -1)
		self.rot_ang.SetValue(str(gRotation_Angle))
		sizer.Add(self.rot_ang, (3, 1), (1, 3), wx.TOP | wx.EXPAND, 5)

		shift_x_txt = wx.StaticText(panel, -1, 'X Shift (unit) :')
		sizer.Add(shift_x_txt, (4, 0), flag= wx.LEFT | wx.TOP, border=10)
		self.shift_x = wx.TextCtrl(panel, -1)
		self.shift_x.SetValue(str(gSHIFT_X))
		sizer.Add(self.shift_x, (4, 1), (1, 1), wx.TOP | wx.EXPAND, 5)

		shift_y_txt = wx.StaticText(panel, -1, 'Y Shift  (unit) :')
		sizer.Add(shift_y_txt, (4, 2), flag= wx.LEFT | wx.TOP, border=10)
		self.shift_y = wx.TextCtrl(panel, -1)
		self.shift_y.SetValue(str(gSHIFT_Y))
		sizer.Add(self.shift_y, (4, 3), (1, 1), wx.TOP | wx.EXPAND, 5)

		button4 = wx.Button(panel, -1, 'Append Open', size=(-1, 30))
		sizer.Add(button4, (6, 2), (1, 1),  wx.LEFT, 10)

		button5 = wx.Button(panel, -1, 'New Open', size=(-1, 30))
		sizer.Add(button5, (6, 3), (1, 1),  wx.LEFT, 10)

		button6 = wx.Button(panel, -1, 'Close', size=(-1, 30))
		sizer.Add(button6, (6, 4), (1, 1),  wx.LEFT | wx.BOTTOM | wx.RIGHT, 10)

		sizer.AddGrowableCol(2)

		panel.SetSizer(sizer)
		sizer.Fit(self)

		# Events
		self.Bind(wx.EVT_BUTTON, self.OnGcodeOpen, button1)
		self.Bind(wx.EVT_BUTTON, self.OnAppend, button4)
		self.Bind(wx.EVT_BUTTON, self.OnNEW, button5)
		self.Bind(wx.EVT_BUTTON, self.OnClose, button6) 
		self.Bind(wx.EVT_RADIOBOX, self.EvtRadioBox1, rb1)

		#self.Bind(wx.EVT_MENU, self.OnExit, menuExit)
		#self.Bind(wx.EVT_MENU, self.OnAbout, menuAbout)

		self.Centre()

		if self._debug:
			# Testfile /Users/johan/Desktop/Rechthoek_45x60.ngc
			self.filename = 'Rechthoek_45x60.ngc'
			self.dirname = '/Users/johan/Desktop'
			print "G-code file:", os.path.join(self.dirname, self.filename)
			self.gcode.SetValue(os.path.join(self.dirname, self.filename))
			self.OnNEW(None)
		else:
			self.ShowModal()

	# Events
	def EvtRadioBox1(self, e):
		if (e.GetInt()==0): # millimeters
			self._inch_flag = 0
		elif (e.GetInt()==1): # Inches
			self._inch_flag = 1
			
	def OnGcodeOpen(self,e):
		"""Open a G-code file."""
		dlg = wx.FileDialog(self, "Choose a output G-code file", self.dirname, "", self._gcode_ext, wx.OPEN)
		if dlg.ShowModal() == wx.ID_OK:
			self.filename = dlg.GetFilename()
			self.dirname = dlg.GetDirectory()
			self.gcode.SetValue(os.path.join(self.dirname, self.filename))
			#print "G-code file:", os.path.join(self.dirname, self.filename)
		dlg.Destroy()

	def OnAppend(self,e):
		"""Add another file to be opened together with a previously selected file or files."""

		global gGCODES, gRotation_Angle, gSHIFT_X, gSHIFT_Y

		if ( self.gcode.GetValue() ):
			gGCODES.append(GCODE(self.gcode.GetValue(), self.gcode_colour.GetValue())) # add G-code file to the list
		if(self.rot_ang.GetValue()):
			gRotation_Angle = int(self.rot_ang.GetValue())
		if(self.shift_x.GetValue()):
			gSHIFT_X = int(self.shift_x.GetValue())
		if(self.shift_y.GetValue()):
			gSHIFT_Y = int(self.shift_y.GetValue())
		set_unit()		
		parseGCodeFile() # parse the G-code file
		self.Close(True)  # close the frame
		
	def OnNEW(self,e):

		global gGCODES, gPATTERNS, gRotation_Angle, gSHIFT_X, gSHIFT_Y

		gGCODES = [] # clear list
		gPATTERNS = []
		if ( self.gcode.GetValue() ):
			gGCODES.append(GCODE(self.gcode.GetValue(), self.gcode_colour.GetValue())) # put G-code file into the list
		if(self.rot_ang.GetValue()):
			gRotation_Angle = int(self.rot_ang.GetValue())
		if(self.shift_x.GetValue()):
			gSHIFT_X = int(self.shift_x.GetValue())
		if(self.shift_y.GetValue()):
			gSHIFT_Y = int(self.shift_y.GetValue())
		set_unit()
		parseGCodeFile() # parse the G-code file
		self.Close(True)  # close the frame
		
	def OnClose(self,e):
		self.Close(True)  # close the frame
		

class POINT:
	def __init__(self, x, y, z):
		self.x = x
		self.y = y
		self.z = z

class LINE:
	def __init__(self, style, line, speed, points):
		self.style = style
		self.line = line
		self.speed = speed
		self.points = points

class ARC:
	def __init__(self, style, line, speed, plane, p1, p2, center):
		self.style = style
		self.line = line
		self.speed = speed
		self.plane = plane
		self.p1 = p1
		self.p2 = p2
		self.center = center

class GCODE:
	def __init__(self, name, colour):
		self.name = name
		self.colour = colour

class PATTERN:
	def __init__(self, colour, patterns):
		self.colour = colour
		self.patterns = patterns
		

# App Entry point
def main():
	app = wx.App(False) # don't redirect stdout/stderr to a window
	#app = wx.App(True) # redirect stdout/stderr to a window
	frame = MainFrame(None, -1, 'pyGerber2Gcode')
	app.MainLoop()

# App Functions
def set_unit(inches=False):
	"""
	Set unit used to inches or millimeters.
	
	@parameter:
	True - inches
	False - millimeters
	
	"""
	global gUNIT

	_inch = 25.4 # millimeters
	_mil = _inch/1000

	if (inches):
		gUNIT = _inch
	else:
		gUNIT = 1.0

def parseGCodeFile():
	"""
	Parse the G-code file.
	The patterns read from the G-Code file(s) are stored in global gPATTERN.
	
	TODO: get rid of the global variable
	
	LinuxCNC G-Code Quick reference: http://linuxcnc.org/docs/html/gcode.html
	
	@parameters
	gGCODES global list of G-Code files
	
	"""
	global gGCODES
	rot_ang = gRotation_Angle * pi/180	
	for gcodes in gGCODES:

		try:
			f = open(gcodes.name,'r')
		except IOError, (errno, strerror):
			error_dialog("Unable to open the file" + gcodes.name + "\n", True)
		else:
			pre_x = 0.0
			pre_y = 0.0
			pre_z = 0.0
			x = pre_x
			y = pre_y
			z = pre_z
			s = 0
			l = 1
			style = 0
			
			patterns = []
			while 1:
				gcode = f.readline()
				if not gcode:
					break
				flag = 0

				#parse G-code
				gg = re.search("[gG]([\d]+)\D", gcode)
				xx = re.search("[xX]([\d\.\-]+)\D", gcode)
				yy = re.search("[yY]([\d\.\-]+)\D", gcode)
				zz = re.search("[zZ]([\d\.\-]+)\D", gcode)
				ss = re.search("[fF]([\d\.\-]+)\D", gcode)

				if (gg):
					style = int(gg.group(1))

				if (xx):
					x = float(xx.group(1))
					flag = 1
				if (yy):
					y = float(yy.group(1))
					flag = 1
				if (zz):
					z = float(zz.group(1))
					flag = 1
					
				if (ss):
					s = float(ss.group(1))

				if (style == 1 or style == 0): # coordinated|fast move
					if (flag):
						center = POINT(0,0,0)
						point1 = POINT(pre_x,pre_y,pre_z)
						point2 = POINT(x,y,z)
						#print point1
						point1 = rot_point(point1, center, rot_ang)
						point1 = shift_point(point1, gSHIFT_X, gSHIFT_Y)
						#print point2
						point2 = rot_point(point2, center, rot_ang)
						point2 = shift_point(point2, gSHIFT_X, gSHIFT_Y)
						patterns.append(LINE(style,l,s,[point1,point2]))
						
				elif (style == 2 or style == 3): # cw|ccw arc feed
						i=0
						j=0
						k=0
						ii = re.search("[iI]([\d\.\-]+)\D", gcode)
						jj = re.search("[jJ]([\d\.\-]+)\D", gcode)
						kk = re.search("[kK]([\d\.\-]+)\D", gcode)
						rr = re.search("[rR]([\d\.\-]+)\D", gcode)
						if (ii):
							i = float(rr.group(1))
						if (jj):
							j = float(rr.group(1))
						if (kk):
							k = float(rr.group(1))
						center = POINT(i,j,k)
						point1 = POINT(pre_x,pre_y,pre_z)
						point2 = POINT(x,y,z)
						if (style == 3):
							tmp_point = point2
							point2 = point1
							point1 = point2
						if (rr):
							r = float(rr.group(1))
							c1,c2 = calc_center(point1,point2,r,plane)
							center = c1
							if (r < 0):
								center = c2
						patterns.append(ARC(style,l,s,plane,point1,point2,center))
						
				elif (style == 17): # XY plane
						plane = 0
						
				elif (style == 18): # XZ plane
						plane = 1
						
				elif (style == 19): # YZ plane
						plane = 2
				
				pre_x = x
				pre_y = y
				pre_z = z					
				l += 1
				
			gPATTERNS.append( PATTERN(gcodes.colour, patterns) )
			f.close()

def calc_center(p1,p2,r,plane):
	"""
	Calculate the center of two points.
	
	@parameters:
	point1
	point2
	rotation angle
	plane:
	0 - XY
	1 - ZX
	2 - YZ
	
	"""
	r = copysign(r, r*r)
	if (plane == 0):	#XY
		if (p1.x == p2.x):
			dx = (p2.x - p1.x)/2
			dy = sqrt(r*r-dx*dx)
			c1 = POINT(p1.x+dx,p1.y+dy,p1.z)
			c2 = POINT(p1.x+dx,p1.y-dy,p1.z)
		elif (p1.y == p2.y):
			dy = (p2.y - p1.y)/2
			dx = sqrt(r*r-dy*dy)
			c1 = POINT(p1.x+dx,p1.y+dy,p1.z)
			c2 = POINT(p1.x-dx,p1.y+dy,p1.z)
		else:
			a = (p2.y - p1.y)/(p2.x - p1.x)
			av = -1/a
			bv = (p2.y -+ p1.y)/2 - av * (p2.x + p1.x)/2
			dx = sqrt(r*r/(av*av+1))
			dy = av * dx
			cx = (p2.x + p1.x)/2
			cy = (p2.y + p1.y)/2
			c1 = POINT(p1.x+dx,p1.y-dy,p1.z)
			c2 = POINT(p1.x-dx,p1.y+dy,p1.z)
#	if (plane == 1):	#ZX
#	if (plane == 2):	#YZ
	return [c1,c2]

def rot_coor(p, c, theta):
	"""
	TODO: Rotate coordinate.
	
	@parameters:
	point
	c
	rotation angle
	
	"""
	dx = c.x-p.x
	dy = c.y-p.y
	ang = atan2(dy,dx) + theta
	r = sqrt(dx*dx+dy*dy)
	
def change_view(p1, p2, c=POINT(0.0, 0.0, 0.0) ):
	"""
	3D to 2D projection.
	
	@parameters:
	point 1
	point 2
	center of rotation
	
	"""
	# for now, fixed angles, in the future these could be input parameters
	theta = pi/4.0
	phi = pi/4.0
	psi = 0.0
	pp1 = POINT(0.0,0.0,0.0)
	pp2 = POINT(0.0,0.0,0.0)
	
	# rotation around z
	dx1 = p1.x-c.x
	dy1 = p1.y-c.y
	r1 = sqrt(dx1*dx1+dy1*dy1)
	ang1 = atan2(dy1,dx1) + theta
	
	dx2 = p2.x-c.x
	dy2 = p2.y-c.y
	r2 = sqrt(dx2*dx2+dy2*dy2)
	ang2 = atan2(dy2,dx2) + theta	

	pp1.x = c.x+r1*cos(ang1)
	pp1.y = c.y+r1*sin(ang1)
	pp2.x = c.x+r2*cos(ang2)
	pp2.y = c.y+r2*sin(ang2)

	# rotation around x
	dy1 = pp1.y-c.y
	dz1 = pp1.z-c.z
	r1 = sqrt(dz1*dz1+dy1*dy1)
	ang1 = atan2(dy1,dz1) + phi
	
	dz2 = pp2.z-c.z
	dy2 = pp2.y-c.y
	r2 = sqrt(dz2*dz2+dy2*dy2)
	ang2 = atan2(dy2,dz2) + phi	

	pp1.z = c.z+r1*cos(ang1)
	pp1.y = c.y+r1*sin(ang1)+p1.z
	pp2.z = c.z+r2*cos(ang2)
	pp2.y = c.y+r2*sin(ang2)+p2.z

	# rotation around y
	dx1 = pp1.x-c.x
	dz1 = pp1.z-c.z
	r1 = sqrt(dz1*dz1+dx1*dx1)
	ang1 = atan2(dx1,dz1) + psi

	dz2 = pp2.z-c.z
	dx2 = pp2.x-c.x
	r2 = sqrt(dz2*dz2+dx2*dx2)
	ang2 = atan2(dx2,dz2) + psi

	pp1.z = c.z+r1*cos(ang1)
	pp1.x = c.y+r1*sin(ang1)
	pp2.z = c.z+r2*cos(ang2)
	pp2.x = c.y+r2*sin(ang2)

	return pp1,pp2

def circle_points(cx,cy,r,points_num):
	"""
	Circle to points.
	
	@parameters:
	x coordinate
	y coordinate
	radius
	number of points
	
	"""
	points=[]
	if (points_num <= 2):
		print "Too small angle at Circle"
		return
	i = points_num
	while i > 0:
		cir_x=cx+r*cos(2.0*pi*float(i)/float(points_num))
		cir_x=cx+r*cos(2.0*pi*float(i)/float(points_num))
		cir_y=cy+r*sin(2.0*pi*float(i)/float(points_num))
		points.extend([cir_x,cir_y])
		i -= 1
	cir_x=cx+r*cos(0.0)
	cir_y=cy+r*sin(0.0)
	points.extend([cir_x,cir_y])
	return points

def arc_points(cx,cy,r,s_angle,e_angle,kaku):
	"""
	Arc to points.
	
	@parameters:
	x coordinate
	y coordinate
	radius
	start angle
	end angle
	angle

	Kaku - Manga character
	Kaku's name most likely comes from the Japanese word "kaku" (角 kaku?, literally meaning "angle"), a reference to his rectangular nose

	"""
	points=[]
	if (s_angle == e_angle):
		print "Start and End angle are same"
	int(kaku)
	if (kaku <= 2):
		print "Too small angle"
	ang_step=(e_angle-s_angle)/(kaku-1)
	i = 0
	while i < kaku:
		arc_x = cx + r*cos(s_angle+ang_step*float(i))
		arc_y = cy + r*sin(s_angle+ang_step*float(i))
		points.extend([arc_x,arc_y])
		i += 1

	return points

def rot_point(point, center, angle):
	dx = center.x - point.x
	dy = point.y - center.y
	initial_angle = atan2(dy,dx)
	r = sqrt(dx*dx + dy*dy)
	ch_angle = initial_angle + angle
	point.x = center.x - r * cos(ch_angle)
	point.y = center.y + r * sin(ch_angle)
	return point

def shift_point(point, xshift, yshift):
	point.x = point.x + xshift
	point.y = point.y + yshift
	return point

def scale_up(point, mag):
	point.x = point.x * mag
	point.y = point.y * mag
	return point


def error_dialog(error_mgs,sw):
	"""
	Print error message and, optionally, quit program.
	
	@parameters:
	error_message
	exit_flag (True - exit program)
	
	"""
	print error_mgs
	if (sw):
		#raw_input("\n\nPress the enter key to exit.")
		sys.exit()

if __name__ == "__main__":
	main()
