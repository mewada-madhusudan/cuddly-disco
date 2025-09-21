# Fixed version of access.py with proper window management
import asyncio
import re
from datetime import datetime

import numpy
import pandas as pd
import urllib3
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QSize, QTimer
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QLineEdit, QMessageBox, QWidget, QStackedWidget,
                             QFrame, QScrollArea, QListWidget, QListWidgetItem, QCheckBox, QComboBox, QProgressDialog,
                             QTextEdit, QTabWidget)
from requests_ntlm import HttpNtlmAuth
from shareplum import Site

from static import SHAREPOINT_LIST, SITE_URL, SID, FIELDS, split_user,LOB, STATUS, pslv_action_entry, user_main

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class FormValidator:
    @staticmethod
    def validate_text(text):
        """Validate text field is not empty and contains valid characters"""
        return bool(text and text.strip() and not re.search('[^]', text))

    @staticmethod
    def validate_app_path(text):
        """Validate text field is not empty and contains an exe path"""
        return True if text.endswith('.exe') else False

    @staticmethod
    def validate_date(date_str):
        """Validate date in DD-MM-YYYY format"""
        try:
            if not date_str:
                return True
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_version(version):
        """Validate version is a valid float"""
        try:
            if not version:
                return True
            float(version)
            return True
        except ValueError:
            return False


class ValidatingLineEdit(QLineEdit):
    def __init__(self, validation_type, required=False, parent=None):
        super().__init__(parent)
        self.validation_type = validation_type
        self.required = required
        self.valid = True
        self.textChanged.connect(self.on_text_changed)

        # Store original stylesheet
        self.default_style = """
            QLineEdit {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
                background: white;
            }
            QLineEdit:focus {
                border: 1px solid #1976d2;
            }
        """
        self.error_style = """
            QLineEdit {
                border: 1px solid #f44336;
                border-radius: 4px;
                padding: 8px;
                background: #fff5f5;
            }
        """
        self.setStyleSheet(self.default_style)

    def validate(self):
        text = self.text().strip()

        # Check if field is required and empty
        if self.required and not text:
            self.set_invalid()
            return False

        # If field is optional and empty, it's valid
        if not self.required and not text:
            self.set_valid()
            return True

        # Validate based on type
        if self.validation_type == 'text':
            valid = FormValidator.validate_text(text)
        elif self.validation_type == 'date':
            valid = FormValidator.validate_date(text)
        elif self.validation_type == 'version':
            valid = FormValidator.validate_version(text)
        elif self.validation_type == 'app':
            valid = FormValidator.validate_app_path(text)
        else:
            valid = True

        if valid:
            self.set_valid()
        else:
            self.set_invalid()

        return valid

    def set_valid(self):
        self.valid = True
        self.setStyleSheet(self.default_style)

    def set_invalid(self):
        self.valid = False
        self.setStyleSheet(self.error_style)

    def on_text_changed(self):
        """Reset validation state when user starts typing"""
        if not self.valid:
            self.setStyleSheet(self.default_style)


class AppTileWidget(QFrame):
    def __init__(self, name, description, parent=None):
        super().__init__(parent)
        self.setObjectName("appTile")
        self.is_selected = False
        self.setFixedSize(300, 100)
        self.setup_ui(name, description)

    def setup_ui(self, name, description):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        # App name with icon in horizontal layout
        name_layout = QHBoxLayout()

        name_label = QLabel(name)
        name_label.setProperty("appName", True)
        name_label.setWordWrap(True)
        name_layout.addWidget(name_label)
        name_layout.addStretch()

        # Description
        desc_label = QLabel(description)
        desc_label.setProperty("appDescription", True)
        desc_label.setWordWrap(True)

        layout.addLayout(name_layout)
        layout.addWidget(desc_label)
        layout.addStretch()

    def set_selected(self, selected):
        self.is_selected = selected
        if selected:
            self.setProperty("selected", True)
        else:
            self.setProperty("selected", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def sizeHint(self):
        return QSize(300, 100)


class VerificationWorker(QObject):
    finished = pyqtSignal(dict)

    def __init__(self, user_ids):
        super().__init__()
        self.user_ids = user_ids

    async def verify_user_id(self, user_id):
        """
        Verify a single user ID using the API
        Replace the URL and any necessary headers/auth for your API
        """
        try:
            # Replace with your actual API endpoint
            response = numpy.get_phonebook_data(user_id)
            return user_id, response['standardID'] == user_id
        except:
            return user_id, False

    async def verify_multiple_ids(self):
        """
        Verify multiple user IDs concurrently
        """
        tasks = [self.verify_user_id(uid) for uid in self.user_ids]
        results = await asyncio.gather(*tasks)
        return {uid: is_valid for uid, is_valid in results}

    def run(self):
        """
        Run the verification process
        """
        async def run_async():
            results = await self.verify_multiple_ids()
            self.finished.emit(results)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_async())
        loop.close()


def is_valid(text):
    return bool(text.strip())


class AccessControlDialog(QDialog):
    def __init__(self, username, lob, parent=None):
        super().__init__(parent)  # FIXED: Ensure proper parent reference
        self.username = username
        self.lob = lob
        self.existing_users_list = None
        self.progress_dialog = None
        self.workers = []  # Keep track of running threads
        self.setWindowTitle("Access Management")
        self.setMinimumSize(900, 600)
        
        # FIXED: Set window modality to prevent separate windows
        self.setWindowModality(Qt.WindowModality.WindowModal)
        
        self.refresh_data()
        self.setup_ui()

    def show_loading_dialog(self):
        """Show an indefinite progress dialog"""
        # FIXED: Ensure progress dialog has proper parent reference
        self.progress_dialog = QProgressDialog("Registering Solution to system...", None, 0, 0, self)
        self.progress_dialog.setWindowTitle("Please Wait")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None)  # Remove cancel button
        self.progress_dialog.setMinimumDuration(0)  # Show immediately
        self.progress_dialog.setStyleSheet("""
            QProgressDialog {
                background-color: white;
                min-width: 300px;
            }
            QLabel {
                color: #333;
                font-size: 13px;
                padding: 10px;
            }
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                text-align: center;
                padding: 1px;
            }
            QProgressBar::chunk {
                background-color: #1976d2;
                border-radius: 3px;
            }
        """)

    def refresh_data(self):
        """Fetch fresh data from the API"""
        try:
            # Create sharepoint session for sharepoint list
            cred = HttpNtlmAuth(SID, "")
            site = Site(SITE_URL, auth=cred, verify_ssl=True)

            # Fetch data from SharePoint list
            sp_list = site.List(SHAREPOINT_LIST)
            sp_data = sp_list.GetListItems(view_name=None)
            df_all = pd.DataFrame(sp_data)
            df_all.fillna('', inplace=True)
            self.df = df_all[df_all['LOB'].isin(self.lob)]
            self.df['Description'] = self.df['Description'].str.slice(0, 50)
            self.df.reset_index(inplace=True, drop=True)
            return True
        except:
            # FIXED: Ensure message box has proper parent reference
            QMessageBox.warning(self, "Refresh Failed",
                                "Failed to load solution list. Kindly retry after sometime.",
                                QMessageBox.StandardButton.Ok)
            return False

    def setup_ui(self):
        # We are combine all large container widget to main space here

        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Left panel
        left_panel = self.setup_left_panel()
        main_layout.addWidget(left_panel)

        # Right panel
        self.right_stack = QStackedWidget(self)  # FIXED: Set proper parent
        self.setup_right_panel()
        main_layout.addWidget(self.right_stack)

        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget#appContainer {
                background-color: #f5f5f5;
                border-right: 1px solid #e0e0e0;
            }
            QWidget#usersContainer {
                background-color: white;
            }
            QScrollArea#usersScrollArea {
                border: none;
                background-color: transparent;
            }
            QWidget#usersListContainer {
                background-color: transparent;
            }
            QDialog {
                background-color: #ffffff;
            }
            QPushButton {
                border: none;
                padding: 8px 16px;
                color: #666;
                text-align: left;
                font-size: 13px;
                border-radius: 4px;
                margin: 2px 8px;
                font-family: Montserrat, serif;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                color: #1976d2;
            }
            QPushButton:checked {
                background-color: #e3f2fd;
                color: #1976d2;
                font-weight: bold;
                font-family: Montserrat, serif;
            }
            QPushButton#actionButton {
                background-color: #1976d2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 100px;
                min-height: 20px;
                text-align: center;
                font-family: Montserrat, serif;
            }
            QPushButton#actionButton:hover {
                background-color: #1565c0;
            }
            QLineEdit {
                border: 1px solid #e0e0e0;
                padding: 8px;
                border-radius: 4px;
                font-size: 13px;
                min-height: 20px;
                background: white;
                font-family: Montserrat, serif;
            }
            QLineEdit:focus {
                border: 1px solid #1976d2;
            }
            QLineEdit:hover {
                border: 2px solid #bbdefb;
            }
            QFrame#leftPanel {
                background-color: #fafafa;
                border-right: 1px solid #e0e0e0;
            }
            QFrame#sidTag {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 4px;
                margin: 4px 0px;
                min-height: 40px;
            }
            QFrame#sidTag:hover {
                border-color: #bbdefb;
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333;
                font-size: 13px;
                font-family: Montserrat, serif;
                text-align: left;
            }
            QLabel[heading="true"] {
                font-size: 15px;
                font-weight: bold;
                color: #1976d2;
                padding: 16px;
                font-family: Montserrat, serif;
                text-align: left;
            }
            QLabel[appheading="true"] {
                font-size: 15px;
                font-weight: bold;
                color: #1976d2;
                padding-bottom: 5px;
                font-family: Montserrat, serif;
                text-align: left;
            }
            QLabel[subheading="true"] {
                font-size: 14px;
                font-weight: 500;
                color: #666;
                padding-bottom: 5px;
                font-family: Montserrat, serif;
                text-align: left;
            }
            QFrame#appTile {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                margin: 4px 5px;
            }
            QFrame#appTile:hover {
                background-color: #f2f5f5;
                border: 1px solid #1976d2;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }
            QFrame#appTile[selected="true"] {
                background-color: #e3f2fd;
                border: 1px solid #1565c0;
            }
            QFrame#appTile[selected="true"]:hover {
                background-color: #e3f2fd;
                border: 1px solid #1565c0;
            }
            QLabel[appName="true"] {
                font-size: 14px;
                font-weight: bold;
                color: #1976d2;
                margin-bottom: 4px;
                font-family: Montserrat, serif;
            }
            QLabel[appDescription="true"] {
                font-size: 12px;
                color: #666;
                line-height: 1.4;
                margin-top: 4px;
                font-family: Montserrat, serif;
            }
            QLabel[appIcon="true"] {
                font-size: 18px;
                color: #1976d2;
            }
            QListWidget#application {
                background-color: #f5f5f5;
                border: none;
                border-radius: 0px;
                padding: 8px 4px;
            }
            QListWidget#application:item {
                padding: 0px;
                margin: 4px 0px;
                border: none;
            }
            QListWidget#application:item:selected {
                padding: 4px 2px;
            }
            QListWidget#application {
                background-color: #f5f5f5;
                border: blue;
                border-radius: 5px;
                padding: 4px 2px;
            }
            QScrollArea {
                border: none;
                background: white;
            }
            QComboBox {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 5px;
                min-height: 20 px;
                background: white;
            }
            QComboBox:disabled {
                background: #f5f5f5;
            }
            QCheckBox {
                spacing: 8px;
                min-height: 36px;
                padding: 4px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QLabel[fieldLabel="true"] {
                font-weight: 500;
                margin-bottom: 4px;
            }
            QLabel[required="true"]:after {
                content: " *";
                color: #f44336;
            }
            QPushButton#secondaryButton {
                background-color: #f5f5f5;
                color: #666;
                border: 1px solid #e0e0e0;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 100px;
                min-height: 20px;
                text-align: center;
                font-family: Montserrat, serif;
            }
            QPushButton::secondaryButton:hover {
                background-color: #e0e0e0;
            }
            """)

    def setup_left_panel(self):
        # left panel QFrame element
        left_panel = QFrame(self)  # FIXED: Set proper parent
        left_panel.setObjectName("leftPanel")
        left_panel.setFixedWidth(220)
        layout = QVBoxLayout(left_panel)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Access Controls", left_panel)  # FIXED: Set proper parent
        title.setProperty("heading", True)
        layout.addWidget(title)

        # Navigation with icons (you can replace with actual icons)
        self.add_app_btn = QPushButton("⊞ Add Application", left_panel)  # FIXED: Set proper parent
        self.manage_access_btn = QPushButton("⚙ Manage Access", left_panel)  # FIXED: Set proper parent

        self.add_app_btn.setCheckable(True)
        self.manage_access_btn.setCheckable(True)

        layout.addWidget(self.add_app_btn)
        layout.addWidget(self.manage_access_btn)
        layout.addStretch()

        self.add_app_btn.clicked.connect(lambda: self.switch_panel(0))
        self.manage_access_btn.clicked.connect(lambda: self.switch_panel(1))

        return left_panel

    def fetch_user_name(self, sid):
        if len(sid.strip()) != 7:
            return
        try:
            data = awmpy.get_phonebook_data(sid)
            self.add_app_fields['Developed_By'].setText(data['nameFull'])
        except Exception as e:
            self.add_app_fields['Developed_By'].clear()

    def eventFilter(self, obj, event):
        if event.type() == event.Type.Wheel:
            if not obj.hasFocus():
                return True
        return super().eventFilter(obj, event)

    def app_filled_widget(self, fields):
        # Method which populates the details of application in widgets
        field_name, label_text, placeholder, options, field_type, validation_type, required = fields
        field_layout = QVBoxLayout()
        field_layout.setSpacing(6)

        # label = QLabel(label_text)
        label = QLabel(label_text + (" *" if required else ""))
        label.setProperty("fieldLabel", True)
        if field_type == "dropdown":
            field = QComboBox(self)  # FIXED: Set proper parent
            field.setPlaceholderText(placeholder)
            if field_name == "LoB":
                options = self.lob
            field.addItems(options)
            field.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            field.setStyleSheet("""
                            QComboBox:item {
                                color: black;
                            }
                            QComboBox:placeholder {
                                color: #bcbcbc;
                            }
                            QComboBox {
                                border: 1px solid #e0e0e0;
                                padding: 8px;
                                border-radius: 4px;
                                font-size: 13px;
                                min-height: 20px;
                                background: white;
                                font-family: Montserrat, serif;
                                color: grey;
                            }
                            QComboBox:focus {
                                border: 1px solid #1976d2;
                            }
                            QComboBox:hover {
                                border: 1px solid #1976d2;
                            }
                            """)
            field.installEventFilter(self)
        else:
            field = ValidatingLineEdit(validation_type, required, parent=self)  # FIXED: Set proper parent
            field.setPlaceholderText(placeholder)
            field.setProperty("formInput", True)
            if field_name == "Developed_By":
                field.textChanged.connect(self.fetch_user_name)

        self.add_app_fields[field_name] = field
        field_layout.addWidget(label)
        field_layout.addWidget(field)
        return field_layout

    def setup_right_panel(self):
        # Add Application Panel
        add_update_widget = QWidget(self)  # FIXED: Set proper parent
        main_layout = QVBoxLayout(add_update_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create fixed header section
        header_widget = QWidget(add_update_widget)  # FIXED: Set proper parent
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(30, 0, 30, 10)
        header_layout.setSpacing(10)

        # Title section
        title = QLabel("Application Details", header_widget)  # FIXED: Set proper parent
        title.setProperty("appheading", True)
        header_layout.addWidget(title)

        description = QLabel("Enter the application details below.", header_widget)  # FIXED: Set proper parent
        description.setProperty("subheading", True)
        header_layout.addWidget(description)

        # Application selection for update mode
        select_layout = QHBoxLayout()
        select_layout.setSpacing(10)
        self.update_mode_checkbox = QCheckBox("Update Existing Application", header_widget)  # FIXED: Set proper parent
        self.app_select_combo = QComboBox(header_widget)  # FIXED: Set proper parent
        self.app_select_combo.setMinimumWidth(400)
        self.app_select_combo.setEnabled(False)
        # Customize the QComboBox appearance using stylesheets
        self.app_select_combo.setStyleSheet("""
            QComboBox {
                background-color: #f0f0f0;
                border: 1px solid #888;
                border-radius: 5px;
                padding: 5px;
                font-size: 14px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::indicator {
                width: 20px;
                height: 20px;
            }
            QComboBox::item {
                padding: 5px;
            }
            QComboBox::item:selected {
                background-color: #007847;
                color: white;
            }
            """)

        select_layout.addWidget(self.update_mode_checkbox)
        select_layout.addWidget(self.app_select_combo)
        select_layout.addStretch()
        header_layout.addLayout(select_layout)

        # Add header to main layout
        main_layout.addWidget(header_widget)

        # Create a scroll area for the form
        scroll_area = QScrollArea(add_update_widget)  # FIXED: Set proper parent
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Create container widget for the form
        form_container = QWidget(scroll_area)  # FIXED: Set proper parent
        add_layout = QVBoxLayout(form_container)
        add_layout.setContentsMargins(30, 20, 30, 20)
        add_layout.setSpacing(10)

        self.add_app_fields = {}
        for field in FIELDS:
            add_layout.addLayout(self.app_filled_widget(field))

        # Button section
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save", form_container)  # FIXED: Set proper parent
        self.save_btn.setObjectName("actionButton")
        self.save_btn.setFixedWidth(140)

        self.clear_btn = QPushButton("Clear Form", form_container)  # FIXED: Set proper parent
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.setFixedWidth(140)

        button_layout.addStretch()
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.save_btn)

        add_layout.addLayout(button_layout)
        add_layout.addStretch()

        # Set the form container as the scroll area widget
        scroll_area.setWidget(form_container)
        main_layout.addWidget(scroll_area)

        # Connect signals
        self.update_mode_checkbox.toggled.connect(self.toggle_update_mode)
        self.app_select_combo.currentTextChanged.connect(self.load_application_data)
        self.save_btn.clicked.connect(self.save_application)
        self.clear_btn.clicked.connect(self.clear_form)

        # Manage Access Panel
        manage_widget = QWidget(self)  # FIXED: Set proper parent
        manage_layout = QVBoxLayout(manage_widget)
        manage_layout.setContentsMargins(0, 0, 0, 0)
        manage_layout.setSpacing(0)

        # Apps list with tiles
        apps_container = QWidget(manage_widget)  # FIXED: Set proper parent
        apps_container.setObjectName("appsContainer")
        apps_layout = QVBoxLayout(apps_container)
        apps_layout.setContentsMargins(10, 0, 20, 20)

        apps_title = QLabel("Applications", apps_container)  # FIXED: Set proper parent
        apps_title.setProperty("appheading", True)

        self.app_list = QListWidget(apps_container)  # FIXED: Set proper parent
        self.app_list.setObjectName("application")
        # self.app_list.setSpacing(10)
        self.app_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.app_list.setViewMode(QListWidget.ViewMode.ListMode)
        self.app_list.setMinimumWidth(350)
        self.app_list.setUniformItemSizes(True)
        # self.app_list.setFixedHeight(app_list())

        apps_layout.addWidget(apps_title)
        apps_layout.addWidget(self.app_list)

        # Users section
        users_container = QWidget(manage_widget)  # FIXED: Set proper parent
        users_container.setObjectName("usersContainer")

        self.setup_user_management(users_container)
        manage_layout.addWidget(apps_container, 1)
        manage_layout.addWidget(users_container, 2)

        self.right_stack.addWidget(add_update_widget)
        self.right_stack.addWidget(manage_widget)

    def update_app_list(self):
        self.app_list.clear()
        if hasattr(self, 'df') and not self.df.empty:
            for _, row in self.df.iterrows():
                item = QListWidgetItem(self.app_list)
                # FIXED: Ensure AppTileWidget has proper parent reference
                tile_widget = AppTileWidget(row['Solution_Name'], row['Description'], parent=self.app_list)
                tile_widget.setFrameShape(QFrame.Shape.StyledPanel)
                # tile_widget.setFixedHeight(QWidget.sizeHint())
                item.setSizeHint(QSize(300, 100))
                item.setData(Qt.ItemDataRole.UserRole, row['Solution_Name'])
                self.app_list.setItemWidget(item, tile_widget)

        self.app_list.itemSelectionChanged.connect(self.handle_selection_changed)

    def handle_selection_changed(self):
        # Update all tiles to unselected state first
        for i in range(self.app_list.count()):
            item = self.app_list.item(i)
            tile_widget = self.app_list.itemWidget(item)
            tile_widget.set_selected(False)

        # Set the selected state for the current item
        current_item = self.app_list.currentItem()
        if current_item:
            tile_widget = self.app_list.itemWidget(current_item)
            tile_widget.set_selected(True)

    def show_success_message(self, message):
        # FIXED: Ensure message box has proper parent reference
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(message)
        msg.setWindowTitle("Success")
        msg.setStyleSheet("""
            QMessageBox {
                background-color: white;
            }
            QMessageBox QPushButton {
                background-color: #1976d2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 100px;
                min-height: 20px;
                text-align: center;
                font-family: Montserrat, serif;
            }
            QMessageBox QPushButton:hover {
                background-color: #1565c0;
            }
            """)
        msg.exec()

    def switch_panel(self, index):
        self.add_app_btn.setChecked(index == 0)
        self.manage_access_btn.setChecked(index == 1)
        self.right_stack.setCurrentIndex(index)

    def save_application(self):
        # Validate all fields
        all_valid = True
        for field_name, input_widget in self.add_app_fields.items():
            if isinstance(input_widget, ValidatingLineEdit):
                if not input_widget.validate():
                    all_valid = False

        if not all_valid:
            # FIXED: Ensure message box has proper parent reference
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please check the form for errors:\n\n" +
                "• Required fields must not be empty\n" +
                "• Dates must be in DD-MM-YYYY format\n" +
                "• Executable Path must contain application name with format\n" +
                "• Version must be a valid number",
                QMessageBox.StandardButton.Ok
            )
            return

        is_update_mode = self.update_mode_checkbox.isChecked()

        # Collect form data
        new_data = {}
        for field, widget in self.add_app_fields.items():
            if isinstance(widget, ValidatingLineEdit):  # QLineEdit for text fields
                new_data[field] = widget.text()
            elif isinstance(widget, QComboBox):  # QComboBox for dropdown fields
                new_data[field] = widget.currentText()
            else:
                raise TypeError(f"Unsupported widget type for field '{field}'")

        if not new_data["Solution_Name"]:
            # FIXED: Ensure message box has proper parent reference
            QMessageBox.warning(self, "Required Field",
                                "Application Name is required.",
                                QMessageBox.StandardButton.Ok)
            return

        try:
            if is_update_mode:
                # Update existing application
                pslv_action_entry([{'SID':user_main, 'action':f'Updated details for app {self.app_name}'}])
                app_name = self.app_select_combo.currentText()
                idx = self.df[self.df['Solution_Name'] == app_name].index[0]
                for field, value in new_data.items():
                    if field in self.df.columns:
                        self.df.at[idx, field] = value
                data_dictionary = self.df.iloc[idx].to_dict()
                self.update_sharepoint_db(dictionary_as_list=[data_dictionary], operation='Update')
            else:
                # Add new application
                pslv_action_entry([{'SID':user_main, 'action':f'New App Registration done: {self.app_name}'}])
                self.df = pd.concat([self.df, pd.DataFrame([new_data])], ignore_index=True)
                self.update_sharepoint_db(dictionary_as_list=[new_data], operation='New')
            # Show loading dialog
            self.show_loading_dialog()
            # Schedule data refresh after a short delay
            QTimer.singleShot(500, self.handle_refresh)
        except:
            # FIXED: Ensure message box has proper parent reference
            QMessageBox.warning(self, "Processing Failed",
                                f"Failed to register solution [{new_data['Solution_Name']}].",
                                QMessageBox.StandardButton.Ok)

    def handle_refresh(self):
        """Handle the data refresh and UI updates"""
        if self.refresh_data():
            # Update UI components
            self.update_app_list()
            self.clear_form()
            # Close the progress dialog
            if self.progress_dialog:
                self.progress_dialog.close()

            # Show success message
            action = "updated" if self.update_mode_checkbox.isChecked() else "added"
            self.show_success_message(f"Application has been {action} successfully!")
        else:
            # FIXED: Ensure message box has proper parent reference
            QMessageBox.warning(self, "Refresh Failed",
                                "Failed to refresh data. Please try again.",
                                QMessageBox.StandardButton.Ok)

    def update_sharepoint_db(self, dictionary_as_list, operation):
        cred = HttpNtlmAuth(SID, "")
        site = Site(SITE_URL, auth=cred, verify_ssl=False)

        # Fetch data from SharePoint list
        sp_list = site.list(SHAREPOINT_LIST)
        sp_list.UpdateListItems(data=dictionary_as_list, kind=operation)

    def toggle_update_mode(self):
        """
        Method created to handle toggle between Add or Update mode
        :return:
        """
        is_update_mode = self.update_mode_checkbox.isChecked()
        self.app_select_combo.setEnabled(is_update_mode)
        self.add_app_fields["Solution_Name"].setEnabled(not is_update_mode)

        if is_update_mode:
            # Populate combo box with application names
            self.app_select_combo.clear()
            self.app_select_combo.addItems(self.df['Solution_Name'].tolist())
            self.save_btn.setText("Update")
        else:
            self.clear_form()
            self.save_btn.setText("Save")

    def load_application_data(self, app_name):
        """
        Methods loads data to form for selected application
        :param app_name:
        :return:
        """
        if not app_name or not self.update_mode_checkbox.isChecked():
            return

        app_data = self.df[self.df['Solution_Name'] == app_name].iloc[0]
        for field_name, input_widget in self.add_app_fields.items():
            if field_name in app_data and field_name not in ['LoB', 'Status']:
                input_widget.setText(str(app_data[field_name]))
            elif field_name in ['LoB', 'Status']:
                value = app_data.get(field_name)
                index = input_widget.findText(value)
                if index >= 0:
                    input_widget.setCurrentIndex(index)

    def clear_form(self):
        """
        method clear the all form field
        :return:
        """
        for field_name, input_widget in self.add_app_fields.items():
            input_widget.clear()
            if field_name == "LoB":
                options = self.lob.tolist()
                input_widget.addItems(options)
            elif field_name == 'Status':
                input_widget.addItems(STATUS)
        self.update_mode_checkbox.setChecked(False)

    def setup_user_management(self, users_container):
        """
        A layout method for users management for the access control
        :param users_container:
        :return:
        """
        users_layout = QVBoxLayout(users_container)
        users_layout.setContentsMargins(20, 0, 20, 20)

        # Title
        users_title = QLabel("Manage Users", users_container)  # FIXED: Set proper parent
        users_title.setProperty("appheading", True)
        users_layout.addWidget(users_title)

        # Tab widget
        tab_widget = QTabWidget(users_container)  # FIXED: Set proper parent
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background: #eef0f0;
            }
            QTabBar::tab {
                background: #f5f5f5;
                border: 1px solid #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #a5d4fa;
                border-bottom-color: #a5d4fa;
            }
            """)

        # Existing Users Tab
        existing_users_tab = QWidget(tab_widget)  # FIXED: Set proper parent
        existing_layout = QVBoxLayout(existing_users_tab)

        existing_label = QLabel("Select users to remove access:", existing_users_tab)  # FIXED: Set proper parent
        existing_label.setProperty("subheading", True)
        existing_layout.addWidget(existing_label)

        self.existing_users_list = QListWidget(existing_users_tab)  # FIXED: Set proper parent
        self.existing_users_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.existing_users_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 5px;
                background: white;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background: #e3f2fd;
                color: #1976d2;
            }
            """)
        existing_layout.addWidget(self.existing_users_list)
        remove_btn = QPushButton("Remove Selected Users", existing_users_tab)  # FIXED: Set proper parent
        remove_btn.setObjectName("actionButton")
        remove_btn.clicked.connect(self.remove_selected_users)
        existing_layout.addWidget(remove_btn)

        # Add Users Tab
        add_users_tab = QWidget(tab_widget)  # FIXED: Set proper parent
        add_layout = QVBoxLayout(add_users_tab)

        add_label = QLabel("Enter user SIDs (one per line):", add_users_tab)  # FIXED: Set proper parent
        add_label.setProperty("subheading", True)
        add_layout.addWidget(add_label)

        self.new_users_text = QTextEdit(add_users_tab)  # FIXED: Set proper parent
        self.new_users_text.setPlaceholderText("Paste multiple IDs or enter one per line")
        self.new_users_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                padding: 8px;
                background: white;
            }
        """)
        add_layout.addWidget(self.new_users_text)

        add_btn = QPushButton("Add Users", add_users_tab)  # FIXED: Set proper parent
        add_btn.setObjectName("actionButton")
        add_btn.clicked.connect(self.add_multiple_users)
        add_layout.addWidget(add_btn)

        # Add tabs to widget
        tab_widget.addTab(existing_users_tab, "Existing Users")
        tab_widget.addTab(add_users_tab, "Add Users")
        users_layout.addWidget(tab_widget)

        def show_application_users(self, current_item):
            if not current_item:
                return

            self.existing_users_list.clear()
            app_name = current_item.data(Qt.ItemDataRole.UserRole)
            app_data = self.df[self.df['Solution_Name'] == app_name].iloc[0]
            users = split_user(app_data['SIDs_For_SolutionAccess'])

            for user in users:
                if user.strip():
                    self.existing_users_list.addItem(user.strip())

            # Ensure the item stays selected
            self.app_list.setCurrentItem(current_item)
            self.current_app_item = current_item

    def remove_selected_users(self):
        """
        Method implements the functionality for removing the selected users from the selected solution
        :return:
        """

        # check if any one solution tile is selected or not, if not selected throws warning box
        if not self.app_list.currentItem():
            # FIXED: Ensure message box has proper parent reference
            QMessageBox.warning(self, "No Application Selected",
                                "Please select an application first.",
                                QMessageBox.StandardButton.Ok)
            return

        # read the users SID from the solution list
        selected_items = self.existing_users_list.selectedItems()
        if not selected_items:
            return

        # read the selected users SID from the list widget :(
        users_to_remove = [item.text() for item in selected_items]
        app_name = self.app_list.currentItem().data(Qt.ItemDataRole.UserRole)

        # Confirmation message before removing the user SIDs
        reply = QMessageBox.question(self, "Confirm Removal",
                                     f"Are you sure you want to remove {len(users_to_remove)} user(s)?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        # check for the user confirmation for removal of user SIDs
        if reply == QMessageBox.StandardButton.Yes:
            # Create progress dialog - FIXED: Ensure proper parent reference
            self.progress = QProgressDialog("Removing user IDs...", None, 0, 0, self)
            self.progress.setWindowTitle("Please Wait")
            self.progress.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress.show()
            app_idx = self.df[self.df['Solution_Name'] == app_name].index[0]
            current_sids = set(self.df.at[app_idx, 'SIDs_For_SolutionAccess'].split(','))
            updated_sids = current_sids - set(users_to_remove)
            try:
                # try removing the user sids
                self.df.at[app_idx, 'SIDs_For_SolutionAccess'] = ','.join(updated_sids)
                self.show_application_users(self.app_list.currentItem())
                data_dictionary = self.df.iloc[app_idx].to_dict()
                self.update_sharepoint_db(dictionary_as_list=[data_dictionary], operation='Update')
                pslv_action_entry([{'SID': user_main, 'action': f'Removed users {users_to_remove} from {app_name}'}])
                self.progress.close()
                self.show_success_message(f"Successfully removed {len(users_to_remove)} user(s)")
            except:
                # on failure revert back the changes of DF
                self.df.at[app_idx, 'SIDs_For_SolutionAccess'] = ','.join(current_sids)
                self.show_application_users(self.app_list.currentItem())
                self.progress.close()
                # FIXED: Ensure message box has proper parent reference
                QMessageBox.warning(self, "Failure",
                                    "Failed to remove user(s)",
                                    QMessageBox.StandardButton.Ok)

    def add_multiple_users(self):
        """
        method for adding multiple/single user to the solution
        :return:
        """

        if not self.app_list.currentItem():
            # FIXED: Ensure message box has proper parent reference
            QMessageBox.warning(self, "No Application Selected",
                                "Please select an application first.",
                                QMessageBox.StandardButton.Ok)
            return

        new_users = self.new_users_text.toPlainText().strip()
        if not new_users:
            return

        # Split by newlines and commas, then clean up
        new_users_list = set()
        for line in new_users.split('\n'):
            new_users_list.update(uid.strip() for uid in line.split(',') if uid.strip())

        if not new_users_list:
            return

        # Create progress dialog - FIXED: Ensure proper parent reference
        self.progress = QProgressDialog("Verifying user IDs...", None, 0, 0, self)
        self.progress.setWindowTitle("Please Wait")
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.show()

        # Create worker thread
        self.thread = QThread(self)  # FIXED: Set proper parent
        self.worker = VerificationWorker(new_users_list)
        self.worker.moveToThread(self.thread)

        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.handle_verification_complete)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # Start the thread
        self.thread.start()

    def handle_verification_complete(self, verification_results):
        """
        Handle the completion of ID verification
        """

        valid_ids = [uid for uid, is_valid in verification_results.items() if is_valid]
        invalid_ids = [uid for uid, is_valid in verification_results.items() if not is_valid]
        self.progress.close()

        if valid_ids:
            # Add verified IDs to the DataFrame
            self.new_users_text.setPlainText(None)
            app_name = self.app_list.currentItem().data(Qt.ItemDataRole.UserRole)
            app_idx = self.df[self.df['Solution_Name'] == app_name].index[0]
            current_sids = set(split_user(self.df.at[app_idx, 'SIDs_For_SolutionAccess']))
            updated_sids = current_sids.union(valid_ids)
            self.df.at[app_idx, 'SIDs_For_SolutionAccess'] = ','.join(updated_sids)
            try:
                # try adding the user sids
                pslv_action_entry([{f'SID': user_main, 'action': f'Added users {valid_ids} to {app_name}'}])
                data_dictionary = self.df.iloc[app_idx].to_dict()
                self.update_sharepoint_db(dictionary_as_list=[data_dictionary], operation='Update')
                self.show_application_users(self.app_list.currentItem())
                self.show_success_message(f"Successfully added {len(valid_ids)} verified user(s)")
            except:
                # on failure revert back the changes of DF
                current_sids = set(split_user(self.df.at[app_idx, 'SIDs_For_SolutionAccess']))
                reverted_sids = current_sids - valid_ids
                self.df.at[app_idx, 'SIDs_For_SolutionAccess'] = ','.join(reverted_sids)
                self.show_application_users(self.app_list.currentItem())
                self.show_success_message(f"Failed to add users, Please try again later... ")

        if invalid_ids:
            # Keep invalid IDs in the text edit
            self.new_users_text.setPlainText('\n'.join(invalid_ids))
            # FIXED: Ensure message box has proper parent reference
            QMessageBox.warning(
                self,
                "Invalid IDs Found",
                f"The following IDs could not be verified and were not added.",
                QMessageBox.StandardButton.Ok
            )
