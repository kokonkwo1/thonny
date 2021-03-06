import tkinter as tk
from tkinter import ttk
from thonny.globals import get_workbench, get_runner
from thonny import ui_utils
from thonny.common import InlineCommand
from thonny.tktextext import TextFrame
import logging
import thonny.memory
import ast
from thonny.misc_utils import shorten_repr
from thonny.ui_utils import update_entry_text, CALM_WHITE
from thonny.gridtable import ScrollableGridTable

class ObjectInspector2(ttk.Frame):
    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        
        self.object_id = None
        self.object_info = None
        
        self._create_general_page()
        self._create_data_page()
        self._create_attributes_page()
        self.active_page = self.data_frame
        self.active_page.grid(row=1, column=0, sticky="nsew")
        
        toolbar = self._create_toolbar()
        toolbar.grid(row=0, column=0, sticky="nsew")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        get_workbench().bind("ObjectSelect", self.show_object, True)
        get_workbench().bind("ObjectInfo", self._handle_object_info_event, True)
        get_workbench().bind("DebuggerProgress", self._handle_progress_event, True)
        get_workbench().bind("ToplevelResult", self._handle_progress_event, True)
        
        #self.demo()
    
    def _create_toolbar(self):
        toolbar = ttk.Frame(self)
        
        self.search_box = ttk.Entry(toolbar, 
                                    #borderwidth=1, 
                                    #background=ui_utils.get_main_background()
                                   )
        self.search_box.grid(row=0, column=0, sticky="nsew", pady=5, padx=5)
        toolbar.columnconfigure(0, weight=1)
        
        self.tabs = []
        
        def create_tab(col, caption, page):
            if page == self.active_page:
                relief = "sunken"
            else:
                relief = "flat"
            tab = tk.Label(toolbar, text=" "+caption+" ", relief=relief, borderwidth=1)
            tab.grid(row=0, column=col, pady=5, padx=5, sticky="nsew")
            self.tabs.append(tab)
            page.tab = tab
            
            def on_click(event):
                if self.active_page == page:
                    return
                else:
                    if self.active_page is not None:
                        self.active_page.grid_forget()
                        self.active_page.tab.configure(relief="flat")
                    
                    self.active_page = page
                    page.grid(row=1, column=0, sticky="nsew")
                    tab.configure(relief="sunken")
                    if (self.active_page == self.attributes_frame
                        and (self.object_info is None
                             or self.object_info["attributes"] == {})):
                        self.request_object_info()
                
            
            tab.bind("<1>", on_click)
        
        create_tab(1, "Overview", self.overview_frame)
        create_tab(2, "Data", self.data_frame)
        create_tab(3, "Atts", self.attributes_frame)
        
        
        def create_navigation_link(col, image_filename, action, tooltip, padx=0):
            button = ttk.Button(toolbar, 
                         #command=handler, 
                         image=get_workbench().get_image(image_filename), 
                         #style="Toolbutton", # TODO: does this cause problems in some Macs?
                         state=tk.NORMAL
                         )
            ui_utils.create_tooltip(button, tooltip,
                       **get_workbench().get_option("theme.tooltip_options", {'padx':3, 'pady':1})
                       )
            
            button.grid(row=0, column=col, sticky=tk.NE, padx=padx, pady=4)
            button.bind("<Button-1>", action)
            return button
        
        
        
        self.back_button = create_navigation_link(7, "nav_backward.gif", self.navigate_back, "Previous object")
        self.forward_button = create_navigation_link(8, "nav_forward.gif", self.navigate_forward, "Next object", (0,10))
        self.back_links = []
        self.forward_links = []
        
        return toolbar
        
    
    def _create_general_page(self):
        self.overview_frame = tk.Frame(self, background=CALM_WHITE)
        
        def _add_main_attribute(row, caption):
            label = tk.Label(self.overview_frame, text=caption + ":  ",
                             background=CALM_WHITE,
                             justify=tk.LEFT)
            label.grid(row=row, column=0, sticky=tk.NW)
            
            value = tk.Entry(self.overview_frame,
                             background=CALM_WHITE,
                             bd=0,
                             readonlybackground=CALM_WHITE,
                             highlightthickness = 0,
                             state="readonly"
                             )
            if row > 0:
                value.grid(row=row, column=1, columnspan=3, 
                       sticky=tk.NSEW, pady=2)
            else:
                value.grid(row=row, column=1, sticky=tk.NSEW, pady=2)
            return value
        
        self.id_entry   = _add_main_attribute(0, "id")
        self.repr_entry = _add_main_attribute(1, "repr")
        self.type_entry = _add_main_attribute(2, "type")
        self.type_entry.config(cursor="hand2", fg="dark blue")
        self.type_entry.bind("<Button-1>", self.goto_type)

    def _create_data_page(self):
        self.data_frame = ttk.Frame(self)
        # type-specific inspectors
        self.current_type_specific_inspector = None
        self.current_type_specific_label = None
        self.type_specific_inspectors = [ 
            FileHandleInspector(self.data_frame),
            FunctionInspector(self.data_frame),
            StringInspector(self.data_frame),
            ElementsInspector(self.data_frame),
            DictInspector(self.data_frame),
            DataFrameInspector(self.data_frame),
            ImageInspector(self.data_frame),
            ReprInspector(self.data_frame)
        ]
        
        self.data_frame.columnconfigure(0, weight=1)
        self.data_frame.rowconfigure(0, weight=1)
    
    def _create_attributes_page(self):
        self.attributes_frame = AttributesFrame(self)        

    
    def navigate_back(self, event):
        if len(self.back_links) == 0:
            return
        
        self.forward_links.append(self.object_id)
        self._show_object_by_id(self.back_links.pop(), True)
    
    def navigate_forward(self, event):
        if len(self.forward_links) == 0:
            return
    
        self.back_links.append(self.object_id)
        self._show_object_by_id(self.forward_links.pop(), True)

    def show_object(self, event):
        self._show_object_by_id(event.object_id)

        
    def _show_object_by_id(self, object_id, via_navigation=False):
        
        if self.winfo_ismapped() and self.object_id != object_id:
            if not via_navigation and self.object_id is not None:
                if self.object_id in self.back_links:
                    self.back_links.remove(self.object_id)
                self.back_links.append(self.object_id)
                del self.forward_links[:]
                
            self.object_id = object_id
            update_entry_text(self.id_entry, thonny.memory.format_object_id(object_id))
            self.set_object_info(None)
            self.request_object_info()
    
    def _handle_object_info_event(self, msg):
        if self.winfo_ismapped():
            if msg.info["id"] == self.object_id:
                if hasattr(msg, "not_found") and msg.not_found:
                    self.object_id = None
                    self.set_object_info(None)
                else:
                    self.set_object_info(msg.info)
    
    def _handle_progress_event(self, event):
        if self.object_id is not None:
            self.request_object_info()
                
                
    def request_object_info(self): 
        if self.active_page is not None:
            frame_width=self.active_page.winfo_width()
            frame_height=self.active_page.winfo_height()
            
            # in some cases measures are inaccurate
            if frame_width < 5 or frame_height < 5:
                frame_width = None
                frame_height = None
            #print("pa", frame_width, frame_height)
        else:
            frame_width=None
            frame_height=None
        
        
        get_runner().send_command(InlineCommand("get_object_info",
                                            object_id=self.object_id,
                                            include_attributes=self.active_page == self.attributes_frame,
                                            all_attributes=False,
                                            frame_width=frame_width,
                                            frame_height=frame_height)) 
                    
    def set_object_info(self, object_info):
        self.object_info = object_info
        if object_info is None:
            update_entry_text(self.repr_entry, "")
            update_entry_text(self.type_entry, "")
            "self.data_frame.child.grid_remove()"
        else:
            update_entry_text(self.repr_entry, object_info["repr"])
            update_entry_text(self.type_entry, object_info["type"])
            self.attributes_frame.tree.configure(height=len(object_info["attributes"]))
            self.attributes_frame.update_variables(object_info["attributes"])
            self.update_type_specific_info(object_info)
                
            
            # update layout
            #self._expose(None)
            #if not self.grid_frame.winfo_ismapped():
            #    self.grid_frame.grid()
        
        """
        if self.back_links == []:
            self.back_label.config(foreground="lightgray", cursor="arrow")
        else:
            self.back_label.config(foreground="blue", cursor="hand2")
    
        if self.forward_links == []:
            self.forward_label.config(foreground="lightgray", cursor="arrow")
        else:
            self.forward_label.config(foreground="blue", cursor="hand2")
        """
    
    def update_type_specific_info(self, object_info):
        type_specific_inspector = None
        for insp in self.type_specific_inspectors:
            if insp.applies_to(object_info):
                type_specific_inspector = insp
                break
        
        #print("TYPSE", type_specific_inspector)
        if type_specific_inspector != self.current_type_specific_inspector:
            if self.current_type_specific_inspector is not None:
                self.current_type_specific_inspector.grid_remove() # TODO: or forget?
                self.current_type_specific_label.destroy()
                self.current_type_specific_inspector = None
                self.current_type_specific_label = None
                
            if type_specific_inspector is not None:
                self.current_type_specific_label = self._add_block_label (3, "")
                
                type_specific_inspector.grid(row=0, 
                                             column=0, 
                                             sticky=tk.NSEW,
                                             padx=(0,10))
                
            self.current_type_specific_inspector = type_specific_inspector
        
        if self.current_type_specific_inspector is not None:
            self.current_type_specific_inspector.set_object_info(object_info,
                                                             self.current_type_specific_label)
    
    def goto_type(self, event):
        if self.object_info is not None:
            get_workbench().event_generate("ObjectSelect", object_id=self.object_info["type_id"])
    
    
    
    def _add_block_label(self, row, caption):
        label = tk.Label(self.overview_frame, bg=ui_utils.CALM_WHITE, text=caption)
        label.grid(row=row, column=0, columnspan=4, sticky="nsew", pady=(20,0))
        return label
        
    

class TypeSpecificInspector:
    def __init__(self, master):
        pass
    
    def set_object_info(self, object_info, label):
        pass
    
    def applies_to(self, object_info):
        return False
    
class FileHandleInspector(TextFrame, TypeSpecificInspector):
    
    def __init__(self, master):
        TypeSpecificInspector.__init__(self, master)
        TextFrame.__init__(self, master, read_only=True)
        self.cache = {} # stores file contents for handle id-s
        self.config(borderwidth=1)
        self.text.configure(background="white")
        self.text.tag_configure("read", foreground="lightgray")
    
    def applies_to(self, object_info):
        return ("file_content" in object_info
                or "file_error" in object_info)
    
    def set_object_info(self, object_info, label):
        
        if "file_content" not in object_info:
            logging.exception("File error: " + object_info["file_error"])
            return
        
        assert "file_content" in object_info
        content = object_info["file_content"]
        line_count_sep = len(content.split("\n"))
        line_count_term = len(content.splitlines())
        char_count = len(content)
        self.text.configure(height=min(line_count_sep, 10))
        self.text.set_content(content)
        
        assert "file_tell" in object_info
        # f.tell() gives num of bytes read (minus some magic with linebreaks)
        
        file_bytes = content.encode(encoding=object_info["file_encoding"])
        bytes_read = file_bytes[0:object_info["file_tell"]]
        read_content = bytes_read.decode(encoding=object_info["file_encoding"])
        read_char_count = len(read_content)
        read_line_count_term = (len(content.splitlines())
                                - len(content[read_char_count:].splitlines()))
        
        pos_index = "1.0+" + str(read_char_count) + "c"
        self.text.tag_add("read", "1.0", pos_index)
        self.text.see(pos_index)
        
        label.configure(text="Read %d/%d %s, %d/%d %s" 
                        % (read_char_count,
                           char_count,
                           "symbol" if char_count == 1 else "symbols",  
                           read_line_count_term,
                           line_count_term,
                           "line" if line_count_term == 1 else "lines"))
            
            
            
class FunctionInspector(TextFrame, TypeSpecificInspector):
    
    def __init__(self, master):
        TypeSpecificInspector.__init__(self, master)
        TextFrame.__init__(self, master, read_only=True)
        self.config(borderwidth=1)
        self.text.configure(background="white")

    def applies_to(self, object_info):
        return "source" in object_info
    
    def set_object_info(self, object_info, label):
        line_count = len(object_info["source"].split("\n"))
        self.text.configure(height=min(line_count, 15))
        self.text.set_content(object_info["source"])
        label.configure(text="Code")
                
            
class StringInspector(TextFrame, TypeSpecificInspector):
    
    def __init__(self, master):
        TypeSpecificInspector.__init__(self, master)
        TextFrame.__init__(self, master, read_only=True)
        self.config(borderwidth=1)
        self.text.configure(background="white")

    def applies_to(self, object_info):
        return object_info["type"] == repr(str)
    
    def set_object_info(self, object_info, label):
        # TODO: don't show too big string
        content = ast.literal_eval(object_info["repr"])
        line_count_sep = len(content.split("\n"))
        line_count_term = len(content.splitlines())
        self.text.configure(height=min(line_count_sep, 10))
        self.text.set_content(content)
        label.configure(text="%d %s, %d %s" 
                        % (len(content),
                           "symbol" if len(content) == 1 else "symbols",
                           line_count_term, 
                           "line" if line_count_term == 1 else "lines"))
        

class ReprInspector(TextFrame, TypeSpecificInspector):
    
    def __init__(self, master):
        TypeSpecificInspector.__init__(self, master)
        TextFrame.__init__(self, master, read_only=True)
        self.config(borderwidth=1)
        self.text.configure(background="white")

    def applies_to(self, object_info):
        return True
    
    def set_object_info(self, object_info, label):
        # TODO: don't show too big string
        content = object_info["repr"]
        self.text.set_content(content)
        """
        line_count_sep = len(content.split("\n"))
        line_count_term = len(content.splitlines())
        self.text.configure(height=min(line_count_sep, 10))
        label.configure(text="%d %s, %d %s" 
                        % (len(content),
                           "symbol" if len(content) == 1 else "symbols",
                           line_count_term, 
                           "line" if line_count_term == 1 else "lines"))
        """
        

class ElementsInspector(thonny.memory.MemoryFrame, TypeSpecificInspector):
    def __init__(self, master):
        TypeSpecificInspector.__init__(self, master)
        thonny.memory.MemoryFrame.__init__(self, master, ('index', 'id', 'value'))
        self.configure(border=1)
        
        #self.vert_scrollbar.grid_remove()
        self.tree.column('index', width=40, anchor=tk.W, stretch=False)
        self.tree.column('id', width=750, anchor=tk.W, stretch=True)
        self.tree.column('value', width=750, anchor=tk.W, stretch=True)
        
        self.tree.heading('index', text='Index', anchor=tk.W) 
        self.tree.heading('id', text='Value ID', anchor=tk.W)
        self.tree.heading('value', text='Value', anchor=tk.W)
    
        self.elements_have_indices = None
        self.update_memory_model()

        get_workbench().bind("ShowView", self.update_memory_model, True)
        get_workbench().bind("HideView", self.update_memory_model, True)
        
        
    def update_memory_model(self, event=None):
        self._update_columns()
        
    def _update_columns(self):
        if get_workbench().in_heap_mode():
            if self.elements_have_indices:
                self.tree.configure(displaycolumns=("index", "id"))
            else:
                self.tree.configure(displaycolumns=("id",))
        else:
            if self.elements_have_indices:
                self.tree.configure(displaycolumns=("index", "value"))
            else:
                self.tree.configure(displaycolumns=("value"))

    def applies_to(self, object_info):
        return "elements" in object_info
    
    def on_select(self, event):
        pass
    
    def on_double_click(self, event):
        self.show_selected_object_info()
    
    def set_object_info(self, object_info, label):
        assert "elements" in object_info
        
        self.elements_have_indices = object_info["type"] in (repr(tuple), repr(list))
        self._update_columns()
        
        self._clear_tree()
        index = 0
        # TODO: don't show too big number of elements
        for element in object_info["elements"]:
            node_id = self.tree.insert("", "end")
            if self.elements_have_indices:
                self.tree.set(node_id, "index", index)
            else:
                self.tree.set(node_id, "index", "")
                
            self.tree.set(node_id, "id", thonny.memory.format_object_id(element["id"]))
            self.tree.set(node_id, "value", shorten_repr(element["repr"], thonny.memory.MAX_REPR_LENGTH_IN_GRID))
            index += 1

        count = len(object_info["elements"])
        self.tree.config(height=min(count,10))
        
        
        label.configure (
            text=("%d element" if count == 1 else "%d elements") % count
        ) 
        

class DictInspector(thonny.memory.MemoryFrame, TypeSpecificInspector):
    def __init__(self, master):
        TypeSpecificInspector.__init__(self, master)
        thonny.memory.MemoryFrame.__init__(self, master, ('key_id', 'id', 'key', 'value'))
        self.configure(border=1)
        #self.vert_scrollbar.grid_remove()
        self.tree.column('key_id', width=100, anchor=tk.W, stretch=False)
        self.tree.column('key', width=100, anchor=tk.W, stretch=False)
        self.tree.column('id', width=750, anchor=tk.W, stretch=True)
        self.tree.column('value', width=750, anchor=tk.W, stretch=True)
        
        self.tree.heading('key_id', text='Key ID', anchor=tk.W) 
        self.tree.heading('key', text='Key', anchor=tk.W) 
        self.tree.heading('id', text='Value ID', anchor=tk.W)
        self.tree.heading('value', text='Value', anchor=tk.W)
    
        self.update_memory_model()
        
    def update_memory_model(self, event=None):
        if get_workbench().in_heap_mode():
            self.tree.configure(displaycolumns=("key_id", "id"))
        else:
            self.tree.configure(displaycolumns=("key", "value"))

    def applies_to(self, object_info):
        return "entries" in object_info

    def on_select(self, event):
        pass
    
    def on_double_click(self, event):
        # NB! this selects value
        self.show_selected_object_info()

    def set_object_info(self, object_info, label):
        assert "entries" in object_info
        
        self._clear_tree()
        # TODO: don't show too big number of elements
        for key, value in object_info["entries"]:
            node_id = self.tree.insert("", "end")
            self.tree.set(node_id, "key_id", thonny.memory.format_object_id(key["id"]))
            self.tree.set(node_id, "key", shorten_repr(key["repr"], thonny.memory.MAX_REPR_LENGTH_IN_GRID))
            self.tree.set(node_id, "id", thonny.memory.format_object_id(value["id"]))
            self.tree.set(node_id, "value", shorten_repr(value["repr"], thonny.memory.MAX_REPR_LENGTH_IN_GRID))

        count = len(object_info["entries"])
        self.tree.config(height=min(count,10))
        
        label.configure (
            text=("%d entry" if count == 1 else "%d entries") % count
        ) 
        
        self.update_memory_model()

class AttributesFrame(thonny.memory.VariablesFrame):
    def __init__(self, master):
        thonny.memory.VariablesFrame.__init__(self, master)
        self.configure(border=1)
        self.vert_scrollbar.grid_remove()
       
    def on_select(self, event):
        pass
    
    def on_double_click(self, event):
        self.show_selected_object_info()
    
class DataFrameInspector(TypeSpecificInspector, tk.Frame):
    def __init__(self, master):
        TypeSpecificInspector.__init__(self, master)
        tk.Frame.__init__(self, master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        self.table = None
        self.columns = None
        self.index = None
        self.values = None
        
        """
        data_row_count = 50
        column_count = 16
        
        header_row = []
        for i in range(column_count):
            header_row.append("Hdr " + str(i) )
        ScrollableGridTable.__init__(self, master, [header_row], 50, 0, 1)
        
        data_rows = {}
        for r in range(data_row_count):
            row = []
            for i in range(column_count):
                row.append("D" + str(r) + ":" + str(i))
            data_rows[r] = row
        self.grid_table.set_data_rows(data_rows)
        """
    
    def set_object_info(self, object_info, label):
        if self.table is not None and self.columns != object_info["columns"]:
            self.table.grid_forget()
            self.table.destroy()
            self.table = None
        
        data = []
        self.columns = object_info["columns"]
        index = object_info["index"]
        values = object_info["values"]
        assert len(values) == len(index)
        for i in range(len(values)):
            data.append([index[i]] + values[i])
        
        headers = [""] + self.columns 
        
        if self.table is None:
            self.table = ScrollableGridTable(self, [headers],
                                             object_info["row_count"], 0, 1)
            
            self.table.grid(row=0, column=0, sticky="nsew")
        
        self.table.grid_table.set_data(data)
    
    def applies_to(self, object_info):
        return object_info.get("is_DataFrame", False)

class ImageInspector(TypeSpecificInspector, tk.Frame):
    def __init__(self, master):
        tk.Frame.__init__(self, master)
        self.label = tk.Label(self, anchor="nw")
        self.label.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def set_object_info(self, object_info, label):
        #print(object_info["image_data"])
        self.image = tk.PhotoImage(data=object_info["image_data"])
        self.label.configure(image=self.image)
    
    def applies_to(self, object_info):
        return "image_data" in object_info
    
        
        
def load_plugin():
    get_workbench().add_view(ObjectInspector2, "Object inspector 2", "se")