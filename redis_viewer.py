import sys
import redis
import base64
import gzip
import snappy
import zstandard
import json
import logging
import os
import traceback
import io

# Configure logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'redis_viewer.log')
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filemode='a'  # Append mode
)

# Create logger instance
logger = logging.getLogger(__name__)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QListWidget, QTextEdit, QPushButton, QLineEdit, QLabel, QSplitter,
    QComboBox, QMessageBox, QInputDialog, QStatusBar, QMenuBar, QMenu,
    QAction, QDialog, QFormLayout, QSpinBox, QGroupBox, QTreeWidget, QTreeWidgetItem,
    QListWidget, QListWidgetItem, QGridLayout, QCheckBox, QHeaderView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

class RedisConnectionThread(QThread):
    result = pyqtSignal(bool, str)
    
    def __init__(self, host, port, password, db):
        super().__init__()
        self.host = host
        self.port = port
        self.password = password
        self.db = db
    
    def run(self):
        try:
            r = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=False
            )
            r.ping()
            self.result.emit(True, "Connected successfully")
        except Exception as e:
            self.result.emit(False, str(e))

class RedisViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.redis_client = None
        self.current_key = None
        self.transform_chain = []
        self.current_transformed_data = None
        
        # 添加配置和历史记录相关变量
        self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        self.chain_history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chain_history.json')
        
        logger.info("Redis Viewer application initialized")
        self.initUI()
        
        # 尝试自动连接Redis（如果配置存在）
        self.load_and_auto_connect()
    
    def initUI(self):
        self.setWindowTitle("Redis Viewer")
        self.setGeometry(100, 100, 1200, 800)
        
        # 设置窗口图标
        try:
            from PyQt5.QtGui import QIcon
            import os
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'redis_icon.png')
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            logger.error(f"Failed to set window icon: {e}")
        
        # Menu Bar
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("&File")
        connect_action = QAction("&Connect", self)
        connect_action.triggered.connect(self.show_connect_dialog)
        file_menu.addAction(connect_action)
        
        exit_action = QAction("&Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        copy_action = QAction("&Copy", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.copy_data)
        edit_menu.addAction(copy_action)
        
        paste_action = QAction("&Paste", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self.paste_data)
        edit_menu.addAction(paste_action)
        
        # Main Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout
        main_layout = QVBoxLayout(central_widget)
        
        # Connection Info - 缩小高度
        self.connection_info = QLabel("Not connected to Redis")
        self.connection_info.setAlignment(Qt.AlignCenter)
        self.connection_info.setStyleSheet("background-color: #f0f0f0; padding: 3px; font-size: 12px;")
        # 设置固定高度以减少空间占用
        self.connection_info.setMaximumHeight(25)
        main_layout.addWidget(self.connection_info)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left Panel - Keys List
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Search Box
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_box = QLineEdit()
        self.search_box.textChanged.connect(self.filter_keys)
        search_button = QPushButton("Refresh")
        search_button.clicked.connect(self.load_keys)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_box)
        search_layout.addWidget(search_button)
        left_layout.addLayout(search_layout)
        
        # Keys List with Search and Filter
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter:")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Keys", "String Keys", "Hash Keys", "List Keys", "Set Keys", "Sorted Set Keys"])
        self.filter_combo.currentIndexChanged.connect(self.filter_keys_by_type)
        
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addStretch()
        left_layout.addLayout(filter_layout)
        
        # Keys List - 使用QTreeWidget以支持树形结构
        self.keys_tree = QTreeWidget()
        self.keys_tree.setHeaderLabel("Keys")
        self.keys_tree.itemClicked.connect(self.load_key_data)
        # 设置列宽以完整显示key名称
        self.keys_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        left_layout.addWidget(self.keys_tree)
        
        splitter.addWidget(left_panel)
        
        # Right Panel - Data View
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Tabs
        self.tabs = QTabWidget()
        
        # Data Tab
        data_tab = QWidget()
        data_tab_layout = QVBoxLayout(data_tab)
        
        # Key Info
        key_info_layout = QHBoxLayout()
        self.key_name_label = QLabel("Key: ")
        self.key_type_label = QLabel("Type: ")
        key_info_layout.addWidget(self.key_name_label)
        key_info_layout.addWidget(self.key_type_label)
        key_info_layout.addStretch()
        data_tab_layout.addLayout(key_info_layout)
        
        # Data Transformation
        transform_group = QGroupBox("Data Transformation")
        transform_layout = QGridLayout(transform_group)
        
        # Transform Combo
        transform_label = QLabel("Transform:")
        self.transform_combo = QComboBox()
        self.transform_combo.addItems([
            "Base64 Decode", "Base64 Encode",
            "Gzip Decompress", "Gzip Compress",
            "Java Gzip Decompress",  # Added for Java Gzip compatibility
            "Snappy Decompress", "Snappy Compress",
            "Zstandard Decompress", "Zstandard Compress",
            "JSON Pretty", "JSON Compact"
        ])
        
        # Transform Buttons
        add_transform_btn = QPushButton("Add to Chain")
        add_transform_btn.clicked.connect(self.add_transform)
        
        apply_chain_btn = QPushButton("Apply Chain")
        apply_chain_btn.clicked.connect(self.apply_transform_chain)
        
        clear_chain_btn = QPushButton("Clear Chain")
        clear_chain_btn.clicked.connect(self.clear_transform_chain)
        
        history_btn = QPushButton("Chain History")
        history_btn.clicked.connect(self.show_chain_history_dialog)
        
        # Transform Chain List
        chain_label = QLabel("Transformation Chain:")
        self.transform_chain_list = QListWidget()
        
        # Layout
        transform_layout.addWidget(transform_label, 0, 0)
        transform_layout.addWidget(self.transform_combo, 0, 1)
        transform_layout.addWidget(add_transform_btn, 0, 2)
        transform_layout.addWidget(apply_chain_btn, 0, 3)
        transform_layout.addWidget(clear_chain_btn, 0, 4)
        transform_layout.addWidget(history_btn, 0, 5)  # Add history button
        transform_layout.addWidget(chain_label, 1, 0, 1, 1)
        transform_layout.addWidget(self.transform_chain_list, 2, 0, 1, 6)  # Update span to 6 columns
        data_tab_layout.addWidget(transform_group)
        
        # Main content splitter for better resizing
        main_content_splitter = QSplitter(Qt.Vertical)
        
        # Data Display - 使用更灵活的布局
        self.data_display = QTextEdit()
        self.data_display.setFont(QFont("Consolas", 10))
        self.data_display.setReadOnly(False)
        # 设置最小大小以改善用户体验
        self.data_display.setMinimumHeight(200)
        
        # Add data display to splitter
        main_content_splitter.addWidget(self.data_display)
        
        # Data Actions
        data_actions_widget = QWidget()  # 创建一个独立的widget来包含操作按钮
        data_actions_layout = QVBoxLayout(data_actions_widget)  # 改为垂直布局
        
        # 按钮行
        buttons_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy Data")
        copy_btn.clicked.connect(self.copy_data)
        
        paste_btn = QPushButton("Paste Data")
        paste_btn.clicked.connect(self.paste_data)
        
        save_btn = QPushButton("Save Data")
        save_btn.clicked.connect(self.save_data)
        
        modify_btn = QPushButton("Modify Key/TTL")
        modify_btn.clicked.connect(self.modify_key_ttl)
        
        buttons_layout.addWidget(copy_btn)
        buttons_layout.addWidget(paste_btn)
        buttons_layout.addWidget(save_btn)
        buttons_layout.addWidget(modify_btn)
        buttons_layout.addStretch()  # 添加伸缩项以对齐按钮
        
        data_actions_layout.addLayout(buttons_layout)
        
        # 将操作区域也添加到分割器中
        main_content_splitter.addWidget(data_actions_widget)
        
        # 设置分割器的拉伸因子，使数据区域占用更多空间
        main_content_splitter.setStretchFactor(0, 3)  # 数据显示区域占用更多空间
        main_content_splitter.setStretchFactor(1, 1)  # 操作按钮区域占用较少空间
        
        # 将分割器添加到主布局
        data_tab_layout.addWidget(main_content_splitter)
        
        self.tabs.addTab(data_tab, "Data")
        
        # Command Tab
        command_tab = QWidget()
        command_layout = QVBoxLayout(command_tab)
        
        # Command Input
        command_input_layout = QHBoxLayout()
        command_label = QLabel("Redis Command:")
        self.command_input = QLineEdit()
        self.command_input.returnPressed.connect(self.execute_command)
        execute_btn = QPushButton("Execute")
        execute_btn.clicked.connect(self.execute_command)
        
        command_input_layout.addWidget(command_label)
        command_input_layout.addWidget(self.command_input)
        command_input_layout.addWidget(execute_btn)
        command_layout.addLayout(command_input_layout)
        
        # Command Output
        self.command_output = QTextEdit()
        self.command_output.setFont(QFont("Consolas", 10))
        self.command_output.setReadOnly(True)
        command_layout.addWidget(self.command_output)
        
        self.tabs.addTab(command_tab, "Commands")
        
        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_panel)
        
        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Initialize
        self.all_keys = []
        self.filtered_keys = []
    
    def show_connect_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Connect to Redis")
        layout = QFormLayout(dialog)
        
        # 从配置文件加载默认值
        config = self.load_config()
        
        host_edit = QLineEdit(config.get('host', 'localhost'))
        port_edit = QSpinBox()
        port_edit.setRange(1, 65535)
        port_edit.setValue(config.get('port', 6379))
        password_edit = QLineEdit(config.get('password', ''))
        password_edit.setEchoMode(QLineEdit.Password)
        db_edit = QSpinBox()
        db_edit.setRange(0, 15)
        db_edit.setValue(config.get('db', 0))
        
        layout.addRow("Host:", host_edit)
        layout.addRow("Port:", port_edit)
        layout.addRow("Password:", password_edit)
        layout.addRow("Database:", db_edit)
        
        # Auto-connect checkbox
        auto_connect_checkbox = QCheckBox("Auto-connect on startup")
        auto_connect_checkbox.setChecked(config.get('auto_connect', False))
        layout.addRow(auto_connect_checkbox)
        
        # Buttons
        button_layout = QHBoxLayout()
        connect_btn = QPushButton("Connect")
        cancel_btn = QPushButton("Cancel")
        
        button_layout.addWidget(connect_btn)
        button_layout.addWidget(cancel_btn)
        layout.addRow(button_layout)
        
        connect_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        if dialog.exec_() == QDialog.Accepted:
            host = host_edit.text()
            port = port_edit.value()
            password = password_edit.text()
            db = db_edit.value()
            auto_connect = auto_connect_checkbox.isChecked()
            
            # 保存配置
            self.save_config(host, port, password, db, auto_connect)
            
            self.connect_to_redis(host, port, password, db)
    
    def connect_to_redis(self, host, port, password, db):
        self.connection_thread = RedisConnectionThread(host, port, password, db)
        self.connection_thread.result.connect(self.on_connection_result)
        self.connection_thread.start()
        
        self.connection_info.setText(f"Connecting to {host}:{port}...")
        
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        return {}
    
    def save_config(self, host, port, password, db, auto_connect):
        """保存配置到文件"""
        try:
            config = {
                'host': host,
                'port': port,
                'password': password,
                'db': db,
                'auto_connect': auto_connect
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            # 不显示错误弹窗，避免打扰用户
    
    def load_and_auto_connect(self):
        """加载配置并尝试自动连接"""
        config = self.load_config()
        if config.get('auto_connect', False):
            host = config.get('host', 'localhost')
            port = config.get('port', 6379)
            password = config.get('password', '')
            db = config.get('db', 0)
            
            self.connect_to_redis(host, port, password, db)
    
    def on_connection_result(self, success, message):
        if success:
            try:
                self.redis_client = redis.Redis(
                    host=self.connection_thread.host,
                    port=self.connection_thread.port,
                    password=self.connection_thread.password,
                    db=self.connection_thread.db,
                    decode_responses=False
                )
                self.connection_info.setText(
                    f"Connected to Redis: {self.connection_thread.host}:{self.connection_thread.port} (DB: {self.connection_thread.db})"
                )
                self.connection_info.setStyleSheet("background-color: #d4edda; padding: 3px; font-size: 12px;")
                logger.info(f"Connected to Redis: {self.connection_thread.host}:{self.connection_thread.port} (DB: {self.connection_thread.db})")
                self.load_keys()
            except Exception as e:
                error_msg = f"Failed to connect to Redis: {str(e)}"
                logger.error(error_msg)
                QMessageBox.critical(self, "Connection Error", error_msg)
        else:
            error_msg = f"Redis connection failed: {message}"
            logger.error(error_msg)
            QMessageBox.critical(self, "Connection Error", message)
            self.connection_info.setText("Not connected to Redis")
            self.connection_info.setStyleSheet("background-color: #f0f0f0; padding: 3px; font-size: 12px;")
    
    def load_keys(self):
        if not self.redis_client:
            return
        
        try:
            self.all_keys = [key.decode('utf-8', errors='replace') for key in self.redis_client.keys("*")]
            self.filtered_keys = self.all_keys.copy()
            
            # Apply type filter
            self.apply_type_filter()
            
            # Update keys list
            self.update_keys_list()
            self.status_bar.showMessage(f"Loaded {len(self.all_keys)} keys, filtered to {len(self.filtered_keys)} keys")
            logger.info(f"Loaded {len(self.all_keys)} keys, filtered to {len(self.filtered_keys)} keys after applying type filter")
        except Exception as e:
            error_msg = f"Failed to load keys: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "Error", error_msg)
    
    def filter_keys(self, text):
        if not text:
            self.filtered_keys = self.all_keys.copy()
        else:
            self.filtered_keys = [key for key in self.all_keys if text.lower() in key.lower()]
        self.update_keys_tree()
    
    def update_keys_list(self):
        """Deprecated, use update_keys_tree instead"""
        self.update_keys_tree()
    
    def update_keys_tree(self):
        """Update the keys list with full key names"""
        self.keys_tree.clear()
        
        # Add each key as a separate item with the full key name
        for key in self.filtered_keys:
            item = QTreeWidgetItem(self.keys_tree)
            item.setText(0, key)  # 显示完整key名称
            item.setData(0, Qt.UserRole, True)  # 标记为实际的key
    
    def load_key_data(self, item):
        if not self.redis_client:
            return
        
        # 直接获取key名称
        key = item.text(0)
        
        self.current_key = key
        
        try:
            key_type = self.redis_client.type(key).decode('utf-8')
            self.key_name_label.setText(f"Key: {key}")
            self.key_type_label.setText(f"Type: {key_type}")
            
            if key_type == 'string':
                value = self.redis_client.get(key)
                self.raw_data = value
                self.current_transformed_data = value
                self.data_display.setPlainText(value.decode('utf-8', errors='replace'))
                self.clear_transform_chain()
                logger.info(f"Loaded string key: {key}, size: {len(value)} bytes")
            elif key_type == 'hash':
                value = self.redis_client.hgetall(key)
                self.raw_data = str(value).encode('utf-8')
                self.current_transformed_data = self.raw_data
                # Format hash data nicely
                hash_str = "\n".join([f"{k.decode('utf-8')}: {v.decode('utf-8')}" for k, v in value.items()])
                self.data_display.setPlainText(hash_str)
                self.clear_transform_chain()
                logger.info(f"Loaded hash key: {key}, fields: {len(value)}")
            elif key_type == 'list':
                value = self.redis_client.lrange(key, 0, -1)
                self.raw_data = str(value).encode('utf-8')
                self.current_transformed_data = self.raw_data
                # Format list data nicely
                list_str = "\n".join([f"{i+1}. {v.decode('utf-8')}" for i, v in enumerate(value)])
                self.data_display.setPlainText(list_str)
                self.clear_transform_chain()
                logger.info(f"Loaded list key: {key}, elements: {len(value)}")
            elif key_type == 'set':
                value = self.redis_client.smembers(key)
                self.raw_data = str(value).encode('utf-8')
                self.current_transformed_data = self.raw_data
                # Format set data nicely
                set_str = "\n".join([v.decode('utf-8') for v in value])
                self.data_display.setPlainText(set_str)
                self.clear_transform_chain()
                logger.info(f"Loaded set key: {key}, elements: {len(value)}")
            elif key_type == 'zset':
                value = self.redis_client.zrange(key, 0, -1, withscores=True)
                self.raw_data = str(value).encode('utf-8')
                self.current_transformed_data = self.raw_data
                # Format zset data nicely
                zset_str = "\n".join([f"{v.decode('utf-8')} (score: {s})" for v, s in value])
                self.data_display.setPlainText(zset_str)
                self.clear_transform_chain()
                logger.info(f"Loaded sorted set key: {key}, elements: {len(value)}")
            else:
                self.raw_data = str(key_type).encode('utf-8')
                self.current_transformed_data = self.raw_data
                self.data_display.setPlainText(f"Unknown type: {key_type}")
                self.clear_transform_chain()
                logger.info(f"Loaded key: {key}, type: {key_type}")
                
        except Exception as e:
            error_msg = f"Failed to load key data: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "Error", error_msg)
    
    def add_transform(self):
        """Add a transform to the transform chain"""
        transform_type = self.transform_combo.currentText()
        self.transform_chain.append(transform_type)
        self.update_transform_chain_list()
    
    def apply_transform_chain(self):
        """Apply the entire transform chain"""
        if not hasattr(self, 'raw_data') or self.raw_data is None:
            return
        
        try:
            # Start with raw data
            data = self.raw_data
            
            # Apply each transform in the chain with detailed logging
            for i, transform_type in enumerate(self.transform_chain):
                logger.debug(f"Applying transform {i+1}/{len(self.transform_chain)}: {transform_type}")
                data = self.apply_single_transform(data, transform_type)
            
            self.current_transformed_data = data
            self.data_display.setPlainText(data.decode('utf-8', errors='replace'))
            logger.info(f"Applied transform chain: {self.transform_chain} on key: {self.current_key}")
            
            # 保存chain历史
            self.save_chain_history()
            
        except Exception as e:
            # Get detailed error information with stack trace
            error_msg = f"Failed to apply transform chain: {str(e)}"
            stack_trace = traceback.format_exc()
            logger.error(f"{error_msg}\nStack trace: {stack_trace}")
            QMessageBox.warning(self, "Transformation Error", f"{error_msg}\n\nCheck logs for detailed information.")
    
    def apply_single_transform(self, data, transform_type):
        """Apply a single transform to the data"""
        if transform_type == "Base64 Decode":
            return base64.b64decode(data)
        elif transform_type == "Base64 Encode":
            return base64.b64encode(data)
        elif transform_type == "Gzip Decompress":
            return self.java_compatible_gzip_decompress(data)
        elif transform_type == "Gzip Compress":
            return gzip.compress(data)
        elif transform_type == "Java Gzip Decompress":
            return self.java_compatible_gzip_decompress(data)
        elif transform_type == "Snappy Decompress":
            # Try different snappy decompression approaches for compatibility with Java Xerial Snappy
            try:
                # First try regular snappy decompress
                return snappy.decompress(data)
            except Exception as e:
                logger.error(f"Regular snappy decompress failed: {e}")
                # Try alternative approach - Java Xerial Snappy compatibility
                try:
                    # Remove Xerial Snappy header if present
                    # Java Xerial Snappy adds a 4-byte magic header: 0x82 0x73 0x6e 0x61 (b'\x82sna')
                    if len(data) >= 4 and data[:4] == b'\x82sna':
                        # Skip Xerial Snappy header and use the raw snappy data
                        return snappy.decompress(data[4:])
                    # Try to decompress without header
                    return snappy.decompress(data)
                except Exception as e2:
                    logger.error(f"Alternative snappy decompress failed: {e2}")
                    raise
        elif transform_type == "Snappy Compress":
            return snappy.compress(data)
        elif transform_type == "Zstandard Decompress":
            dctx = zstandard.ZstdDecompressor()
            return dctx.decompress(data)
        elif transform_type == "Zstandard Compress":
            cctx = zstandard.ZstdCompressor()
            return cctx.compress(data)
        elif transform_type == "JSON Pretty":
            json_data = json.loads(data.decode('utf-8'))
            return json.dumps(json_data, indent=2).encode('utf-8')
        elif transform_type == "JSON Compact":
            json_data = json.loads(data.decode('utf-8'))
            return json.dumps(json_data).encode('utf-8')
        return data
    
    def java_compatible_gzip_decompress(self, data):
        """
        Java兼容的Gzip解压缩方法，能处理Java生成的Gzip数据
        """
        try:
            # 首先尝试标准的gzip解压缩
            return gzip.decompress(data)
        except Exception as e:
            logger.error(f"Standard gzip decompress failed: {e}")
            try:
                # 尝试使用GzipFile进行更灵活的解压缩
                buffer = io.BytesIO(data)
                with gzip.GzipFile(fileobj=buffer, mode='rb') as gz_file:
                    return gz_file.read()
            except Exception as e2:
                logger.error(f"GzipFile decompress failed: {e2}")
                # 尝试跳过可能的头信息或额外字节
                try:
                    # 如果数据以gzip魔数开头(1f8b)，但标准方法失败，尝试手动处理
                    if len(data) >= 2 and data[0] == 0x1f and data[1] == 0x8b:
                        # 这是gzip格式，但可能需要特殊处理
                        # 有些Java实现可能在数据末尾添加额外信息
                        # 尝试找到gzip数据的实际长度
                        buffer = io.BytesIO(data)
                        with gzip.GzipFile(fileobj=buffer, mode='rb') as gz_file:
                            result = gz_file.read()
                            return result
                except Exception as e3:
                    logger.error(f"Manual gzip processing failed: {e3}")
                    raise e  # 如果所有方法都失败，抛出原始异常
    
    def clear_transform_chain(self):
        """Clear the transform chain"""
        self.transform_chain.clear()
        self.update_transform_chain_list()
    
    def save_chain_history(self):
        """保存chain历史到文件"""
        try:
            # 限制历史记录数量，避免文件过大
            max_history = 50
            
            # 加载现有历史
            history = self.load_chain_history()
            
            # 添加当前chain到历史记录
            if self.transform_chain and self.transform_chain not in history:
                history.insert(0, self.transform_chain.copy())
                
                # 限制历史记录数量
                if len(history) > max_history:
                    history = history[:max_history]
                
                # 保存历史记录
                with open(self.chain_history_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save chain history: {e}")
    
    def load_chain_history(self):
        """从文件加载chain历史"""
        try:
            if os.path.exists(self.chain_history_file):
                with open(self.chain_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load chain history: {e}")
        return []
    
    def show_chain_history_dialog(self):
        """显示chain历史对话框"""
        history = self.load_chain_history()
        
        if not history:
            QMessageBox.information(self, "Chain History", "No chain history found.")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Chain History")
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # 历史列表
        history_list = QListWidget()
        for i, chain in enumerate(history):
            chain_str = " -> ".join(chain)
            item = QListWidgetItem(f"{i+1}. {chain_str}")
            item.setData(Qt.UserRole, chain)  # 存储实际chain数据
            history_list.addItem(item)
        
        layout.addWidget(history_list)
        
        # 按钮
        button_layout = QHBoxLayout()
        load_btn = QPushButton("Load Selected")
        clear_btn = QPushButton("Clear History")
        close_btn = QPushButton("Close")
        
        button_layout.addWidget(load_btn)
        button_layout.addWidget(clear_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        def load_selected():
            current_item = history_list.currentItem()
            if current_item:
                chain = current_item.data(Qt.UserRole)
                self.transform_chain = chain.copy()
                self.update_transform_chain_list()
                dialog.close()
        
        def clear_history():
            reply = QMessageBox.question(self, "Clear History", "Are you sure you want to clear all chain history?", 
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    if os.path.exists(self.chain_history_file):
                        os.remove(self.chain_history_file)
                    history_list.clear()
                    QMessageBox.information(self, "Clear History", "Chain history cleared.")
                except Exception as e:
                    logger.error(f"Failed to clear chain history: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to clear history: {str(e)}")
        
        load_btn.clicked.connect(load_selected)
        clear_btn.clicked.connect(clear_history)
        close_btn.clicked.connect(dialog.close)
        
        dialog.exec_()
    
    def update_transform_chain_list(self):
        """Update the transform chain list display"""
        self.transform_chain_list.clear()
        for transform in self.transform_chain:
            self.transform_chain_list.addItem(transform)
    
    def filter_keys_by_type(self):
        """Filter keys by type"""
        if not self.redis_client:
            return
        
        self.load_keys()
    
    def filter_keys(self, text):
        """Filter keys by search text"""
        if not text:
            self.filtered_keys = self.all_keys.copy()
        else:
            self.filtered_keys = [key for key in self.all_keys if text.lower() in key.lower()]
        
        # Apply type filter if needed
        self.apply_type_filter()
        self.update_keys_list()
    
    def apply_type_filter(self):
        """Apply type filter to the keys"""
        if self.filter_combo.currentText() == "All Keys":
            return
        
        # Create a copy of filtered keys to avoid modifying the original
        temp_keys = self.filtered_keys.copy()
        self.filtered_keys = []
        
        for key in temp_keys:
            try:
                key_type = self.redis_client.type(key).decode('utf-8')
                filter_type = self.filter_combo.currentText().lower()
                
                if (filter_type == "string keys" and key_type == "string") or \
                   (filter_type == "hash keys" and key_type == "hash") or \
                   (filter_type == "list keys" and key_type == "list") or \
                   (filter_type == "set keys" and key_type == "set") or \
                   (filter_type == "sorted set keys" and key_type == "zset"):
                    self.filtered_keys.append(key)
            except Exception:
                continue
    
    def update_keys_list(self):
        """Deprecated, use update_keys_tree instead"""
        self.update_keys_tree()
    
    def copy_data(self):
        selected_text = self.data_display.textCursor().selectedText()
        if selected_text:
            QApplication.clipboard().setText(selected_text)
            self.status_bar.showMessage("Text copied to clipboard")
        else:
            all_text = self.data_display.toPlainText()
            QApplication.clipboard().setText(all_text)
            self.status_bar.showMessage("All data copied to clipboard")
    
    def paste_data(self):
        if not self.current_key or not self.redis_client:
            QMessageBox.warning(self, "Warning", "No key selected or not connected to Redis")
            return
        
        paste_text = QApplication.clipboard().text()
        try:
            self.redis_client.set(self.current_key, paste_text.encode('utf-8'))
            self.raw_data = paste_text.encode('utf-8')
            self.status_bar.showMessage(f"Data pasted to key: {self.current_key}")
            logger.info(f"Pasted data to key: {self.current_key}, size: {len(paste_text)} bytes")
        except Exception as e:
            error_msg = f"Failed to paste data to key: {self.current_key}, Error: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "Error", error_msg)
    
    def save_data(self):
        if not self.current_key or not self.redis_client:
            QMessageBox.warning(self, "Warning", "No key selected or not connected to Redis")
            return
        
        data = self.data_display.toPlainText()
        try:
            self.redis_client.set(self.current_key, data.encode('utf-8'))
            self.raw_data = data.encode('utf-8')
            self.status_bar.showMessage(f"Data saved to key: {self.current_key}")
            logger.info(f"Saved data to key: {self.current_key}, size: {len(data)} bytes")
        except Exception as e:
            error_msg = f"Failed to save data to key: {self.current_key}, Error: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "Error", error_msg)
    
    def modify_key_ttl(self):
        if not self.current_key or not self.redis_client:
            QMessageBox.warning(self, "Warning", "No key selected or not connected to Redis")
            return
        
        # 获取当前TTL
        try:
            current_ttl = self.redis_client.ttl(self.current_key)
            ttl_text = str(current_ttl) if current_ttl != -1 else "-1 (No expiration)"
            
            # 显示修改对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("Modify Key and TTL")
            dialog.resize(400, 200)
            
            layout = QFormLayout(dialog)
            
            # Key名称输入框
            key_input = QLineEdit(self.current_key)
            layout.addRow("Key Name:", key_input)
            
            # 当前key名称显示
            current_key_label = QLabel(f"Current Key: {self.current_key}")
            layout.addRow(current_key_label)
            
            # TTL输入框
            ttl_input = QLineEdit(str(current_ttl if current_ttl != -1 else ""))
            layout.addRow("TTL (seconds, leave empty for no expiration):", ttl_input)
            
            # 按钮
            button_layout = QHBoxLayout()
            ok_btn = QPushButton("OK")
            cancel_btn = QPushButton("Cancel")
            
            ok_btn.clicked.connect(dialog.accept)
            cancel_btn.clicked.connect(dialog.reject)
            
            button_layout.addWidget(ok_btn)
            button_layout.addWidget(cancel_btn)
            layout.addRow(button_layout)
            
            if dialog.exec_() == QDialog.Accepted:
                new_key = key_input.text().strip()
                ttl_text = ttl_input.text().strip()
                
                if not new_key:
                    QMessageBox.warning(self, "Warning", "Key name cannot be empty")
                    return
                
                try:
                    data = self.data_display.toPlainText()
                    
                    # 如果key名称改变了，需要删除旧key并创建新key
                    if new_key != self.current_key:
                        # 删除旧key
                        self.redis_client.delete(self.current_key)
                        # 创建新key
                        self.redis_client.set(new_key, data.encode('utf-8'))
                        
                        # 更新当前key
                        old_key = self.current_key
                        self.current_key = new_key
                        
                        # 更新界面显示
                        self.key_name_label.setText(f"Key: {new_key}")
                        self.status_bar.showMessage(f"Key renamed from '{old_key}' to '{new_key}'")
                        logger.info(f"Key renamed from '{old_key}' to '{new_key}'")
                    else:
                        # 只是更新TTL，数据保持不变
                        # 先检查是否有修改数据
                        if data.encode('utf-8') != self.raw_data:
                            # 如果数据被修改了，更新数据
                            self.redis_client.set(self.current_key, data.encode('utf-8'))
                        # 如果数据没有修改，只设置TTL
                        
                    # 设置TTL（如果提供了有效值）
                    if ttl_text:
                        ttl_value = int(ttl_text)
                        if ttl_value > 0:
                            self.redis_client.expire(self.current_key, ttl_value)
                            self.status_bar.showMessage(f"Data and TTL updated for key: {self.current_key}")
                            logger.info(f"TTL {ttl_value}s set for key: {self.current_key}")
                        elif ttl_value == 0:
                            # 如果TTL为0，删除key
                            self.redis_client.delete(self.current_key)
                            self.status_bar.showMessage(f"Key '{self.current_key}' deleted due to TTL=0")
                            logger.info(f"Key '{self.current_key}' deleted due to TTL=0")
                        else:
                            # 如果TTL为负数，移除过期时间
                            self.redis_client.persist(self.current_key)
                            self.status_bar.showMessage(f"TTL removed for key: {self.current_key}")
                            logger.info(f"TTL removed for key: {self.current_key}")
                    else:
                        # 如果没有提供TTL值，也移除过期时间
                        self.redis_client.persist(self.current_key)
                        
                    # 刷新键列表
                    self.load_keys()
                    
                except ValueError:
                    QMessageBox.critical(self, "Error", "Invalid TTL value. Please enter a valid number.")
                except Exception as e:
                    error_msg = f"Failed to modify key: {str(e)}"
                    logger.error(error_msg)
                    QMessageBox.critical(self, "Error", error_msg)
        
        except Exception as e:
            error_msg = f"Failed to get TTL for key: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "Error", error_msg)
    
    def execute_command(self):
        if not self.redis_client:
            QMessageBox.warning(self, "Warning", "Not connected to Redis")
            return
        
        command = self.command_input.text().strip()
        if not command:
            return
        
        try:
            # Split command into parts
            cmd_parts = command.split()
            if not cmd_parts:
                return
            
            cmd = cmd_parts[0].lower()
            args = cmd_parts[1:]
            
            logger.info(f"Executing Redis command: {command}")
            
            # Execute command
            result = self.redis_client.execute_command(cmd, *args)
            
            # Display result
            if isinstance(result, bytes):
                result_str = result.decode('utf-8', errors='replace')
            elif isinstance(result, list):
                result_str = '\n'.join([
                    item.decode('utf-8', errors='replace') if isinstance(item, bytes) else str(item)
                    for item in result
                ])
            else:
                result_str = str(result)
            
            self.command_output.append(f"> {command}")
            self.command_output.append(result_str)
            self.command_output.append("=" * 50)
            
            logger.info(f"Command executed successfully: {command}")
            
            # Clear input
            self.command_input.clear()
            
        except Exception as e:
            error_msg = f"Command failed: {command}, Error: {str(e)}"
            logger.error(error_msg)
            self.command_output.append(f"> {command}")
            self.command_output.append(f"Error: {str(e)}")
            self.command_output.append("=" * 50)
    
if __name__ == "__main__":
    logger.info("Starting Redis Viewer application")
    app = QApplication(sys.argv)
    window = RedisViewer()
    window.show()
    result = app.exec_()
    logger.info("Exiting Redis Viewer application")
    sys.exit(result)
