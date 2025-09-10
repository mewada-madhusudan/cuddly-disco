"""
Solution Launcher Window - FIXED VERSION
================================================================================
This Module contains the code related to the functionality of listing, installing and managing the solution allowed
for user. FIXED to address UI responsiveness issues by implementing proper threading for all blocking operations.

Contains implementation of EnvironmentLabel, ApplicationTile, NoAccessWidget, MainWindow, InstallThread
ADDED: RefreshWorker, AdminCheckWorker, UserDetailsWorker for non-blocking operations
"""

# Python default package imports
import getpass
import os
import shutil
from datetime import datetime
import datetime, timedelta

# Python third party package imports
import awmpy
import pandas as pd
import numpy as np
import urllib3
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer, QObject
from PyQt6.QtGui import QPixmap, QIcon, QFont, QDesktopServices, QMouseEvent
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QGridLayout, QFrame, QProgressBar, QMessageBox,
                             QScrollArea, QStackedLayout, QSpacerItem, QMenu, QStackedWidget, QDialog, QProgressDialog)
from requests_ntlm import HttpNtlmAuth
from shareplum import Site

# User created module for functionalities
from access import AccessControlDialog
from security_check import LauncherSecurity
from static import resource_path, BETA, UAT, PROD, APP_DIR, expire_sort, DETAILS, SITE_URL, SID, SHAREPOINT_LIST, \
    BACKUP_FILE_NAME, BACKUP_PATH, STO_CONFIG, LOB, ADMIN, pslv_action_entry, add_new_user_to_userbase

# global variable for user id
user_main = getpass.getuser()


class RefreshWorker(QThread):
    """Worker thread for refreshing applications data from SharePoint"""
    data_loaded = pyqtSignal(object)  # Emits the processed DataFrame
    error_occurred = pyqtSignal(str)  # Emits error message
    progress_updated = pyqtSignal(str)  # Emits progress message

    def __init__(self):
        super().__init__()
        self.should_stop = False

    def run(self):
        """Run the refresh operation in background thread"""
        try:
            self.progress_updated.emit("Connecting to SharePoint...")
            
            user = user_main.lower()
            # Initialize SharePoint client with timeout
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            cred = HttpNtlmAuth(SID, password="")

            # Create site connection with timeout
            site = Site(SITE_URL, auth=cred, verify_ssl=False, timeout=30)
            
            if self.should_stop:
                return

            self.progress_updated.emit("Fetching application data...")
            
            # Fetch data from SharePoint list
            sp_list = site.List(SHAREPOINT_LIST)
            sp_data = sp_list.GetListItems(view_name=None)
            
            if self.should_stop:
                return
                
            self.progress_updated.emit("Processing data...")
            
            df_all = pd.DataFrame(sp_data)
            df_all.fillna(value='', inplace=True)
            df_all['SIDs_For_SolutionAccess'] = df_all['SIDs_For_SolutionAccess'].str.lower()
            all_df = df_all[df_all['SIDs_For_SolutionAccess'].str.contains('everyone', na=False)]
            processed_df = df_all[df_all['SIDs_For_SolutionAccess'].str.contains(user, na=False)]
            processed_df = pd.concat([all_df, processed_df])
            processed_df.reset_index(inplace=True, drop=True)
            
            # Save backup
            try:
                os.makedirs(f"{os.environ.get('USERPROFILE')}/{BACKUP_PATH}", exist_ok=True)
                processed_df.to_excel(
                    excel_writer=f"{os.environ.get('USERPROFILE')}/{BACKUP_PATH}/{BACKUP_FILE_NAME}",
                    index=False
                )
            except Exception as backup_error:
                print(f"Warning: Could not save backup: {backup_error}")
            
            self.data_loaded.emit(processed_df)
            
        except Exception as e:
            # Try to load from backup
            try:
                backup_path = f"{os.environ.get('USERPROFILE')}/{BACKUP_PATH}/{BACKUP_FILE_NAME}"
                if os.path.exists(backup_path):
                    processed_df = pd.read_excel(backup_path)
                    self.data_loaded.emit(processed_df)
                    self.error_occurred.emit("Loaded from backup due to connection error")
                else:
                    empty_df = pd.DataFrame(
                        columns=['Expired', 'Solution_Name', 'Description', 'ApplicationExePath', 'Status',
                                'Release_Date', 'Validity_Period', 'Version_Number', 'UMAT_IAHub_ID'])
                    self.data_loaded.emit(empty_df)
                    self.error_occurred.emit("No backup available. Please check your connection.")
            except Exception as backup_error:
                empty_df = pd.DataFrame(
                    columns=['Expired', 'Solution_Name', 'Description', 'ApplicationExePath', 'Status',
                            'Release_Date', 'Validity_Period', 'Version_Number', 'UMAT_IAHub_ID'])
                self.data_loaded.emit(empty_df)
                self.error_occurred.emit(f"Failed to refresh: {str(e)}")

    def stop(self):
        """Stop the worker thread"""
        self.should_stop = True


class AdminCheckWorker(QThread):
    """Worker thread for checking administrator privileges"""
    admin_check_complete = pyqtSignal(bool, object)  # is_admin, managed_lob
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def run(self):
        """Check administrator privileges in background thread"""
        try:
            cred = HttpNtlmAuth(SID, password="")
            site = Site(SITE_URL, auth=cred, verify_ssl=False, timeout=30)
            
            # Fetch data from SharePoint list
            sp_list = site.List(ADMIN)
            query = {'Where': [('Contains', 'sid', user_main)]}
            
            # Fetch items with the query and row limit
            sp_data = sp_list.GetListItems(query=query)
            df = pd.DataFrame(sp_data)
            df.fillna(value='', inplace=True)
            managed_lob = df['lob'].tolist()
            
            is_admin = len(managed_lob) > 0
            self.admin_check_complete.emit(is_admin, managed_lob)
            
        except Exception as e:
            self.admin_check_complete.emit(False, [])
            self.error_occurred.emit(f"Failed to check admin privileges: {str(e)}")


class UserDetailsWorker(QThread):
    """Worker thread for fetching user details from phonebook API"""
    user_details_loaded = pyqtSignal(list, str)  # details, cost_center
    error_occurred = pyqtSignal(str)

    def __init__(self, userdata):
        super().__init__()
        self.userdata = userdata

    def run(self):
        """Fetch user details in background thread"""
        try:
            if self.userdata.empty:
                # Call phonebook API with timeout handling
                data = awmpy.get_phonebook_data(user_main)
                cost_center = data['costCenterID']
                data['email'] = data['email'].replace('@', '@ ')
                details = [
                    (data['standardID'], 'icons8-id-50.png'),
                    (data['nameFull'], 'icons8-user-64.png'),
                    (data['email'], 'icons8-email-50.png'),
                    (data['jobTitle'], 'icons8-new-job-50.png'),
                    (data['buildingName'], 'icons8-location-50.png')
                ]
                
                # Add user to userbase in background
                try:
                    add_new_user_to_userbase(
                        [data['standardID'], data['nameFull'], data['email'], 
                         data['jobTitle'], data['buildingName'], data['costCenterID']]
                    )
                except Exception as add_error:
                    print(f"Warning: Could not add user to userbase: {add_error}")
                    
            else:
                cost_center = self.userdata['cost_center_id'].values[0]
                details = [
                    (self.userdata['sid'].values[0], 'icons8-id-50.png'),
                    (self.userdata['display_name'].values[0], 'icons8-user-64.png'),
                    (self.userdata['email'].values[0], 'icons8-email-50.png'),
                    (self.userdata['job_title'].values[0], 'icons8-new-job-50.png'),
                    (self.userdata['building_name'].values[0], 'icons8-location-50.png')
                ]
            
            self.user_details_loaded.emit(details, cost_center)
            
        except Exception as e:
            # Fallback to default details
            self.user_details_loaded.emit(DETAILS, "")
            self.error_occurred.emit(f"Failed to fetch user details: {str(e)}")


class EnvironmentLabel(QLabel):  # Usage - Mewada,Madhusudan
    """
    QLabel inherited custom element for displaying solution deployed environment
    Allowed Environment : UAT/BETA/PROD
    """

    def __init__(self, env_type, parent=None):  # Mewada,Madhusudan
        """
        Initialization of QLabel customized instance
        :param env_type: UAT/BETA/PROD as string
        :param parent:
        """
        if len(env_type) > 4:
            env_type = env_type[:5]
        super().__init__(env_type, parent)
        self.env_type = env_type
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Style based on environment type
        if env_type == "PROD":
            bg_color = PROD
        elif env_type == "UAT":  # UAT
            bg_color = UAT
        else:
            bg_color = BETA

        self.setStyleSheet(f"""
            background-color: {bg_color};
            color: white;
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: bold;
            font-family: Montserrat, serif;
        """)
        self.setFixedHeight(20)
        self.setFixedWidth(60)


class InstallThread(QThread):  # Usage - Mewada,Madhusudan
    """
    InstallThread a thread inherited class, which handles installation/copy of program from sharedrive to user system
    """

    progress = pyqtSignal(int)  # progress signal for installation progress
    finished = pyqtSignal()  # installation finish signal
    error = pyqtSignal(str)  # Error signal for handling error in installation

    def __init__(self, source, destination):  # Mewada,Madhusudan
        """
        initialize the source and destination location for solution
        :param source: path (string)
        :param destination: path (string)
        """
        super().__init__()
        self.source = source
        self.destination = destination

    def run(self):  # Mewada,Madhusudan
        """
        thread function which handles solution movement in chunk to keep faster speed and show progress
        :return:
        """
        try:
            if not os.path.exists(self.source):
                raise FileNotFoundError(f"Source file not found: {self.source}")

            total_size = os.path.getsize(self.source)  # fetch size of solution
            copied_size = 0  # initialize the copied size to 0
            with open(self.source, 'rb') as src, open(self.destination, 'wb') as dst:
                # copy the chunked data till file is copied completely
                while True:
                    chunk = src.read(1024)
                    if not chunk:
                        break
                    dst.write(chunk)
                    copied_size += len(chunk)
                    progress = int((copied_size / total_size) * 100)
                    self.progress.emit(progress)
            self.finished.emit()
        except FileNotFoundError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Installation error: {str(e)}")


class ApplicationTile(QFrame):  # 2 usages - Mewada,Madhusudan
    """
    Custom Application Tile based on QFrame containing all necessary tile elements
    """

    def __init__(self, app_name, app_description, shared_drive_path, environment,  # Mewada,Madhusudan
                 release_date, validity_period, version_number, registration_id, parent=None):
        # Initialization of all variables and sub UI elements
        super().__init__(parent)
        # Store all the data
        self.elements = None
        self.app_name = app_name
        self.app_description = app_description
        self.shared_drive_path = shared_drive_path
        self.environment = environment
        self.release_date = release_date
        self.validity_period = validity_period
        self.version_number = version_number  # This is the version from DB
        self.registration_id = registration_id

        # Set up paths and database connection
        self.install_path = os.environ.get('USERPROFILE')  # %USERPROFILE%
        self.install_path = os.path.join(f"{self.install_path}\\{APP_DIR}", app_name)

        # Initialize version tracking
        self.installed_version = self.get_installed_version()
        self.installed = self.is_app_installed(f"{self.install_path}" + "\\" + f"{self.app_name}.exe")

        # set context policy
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Check status
        self.is_expired = self.check_validity()
        self.update_available = self.check_update_available()

        # Initialize flip state
        self.is_flipped = False

        # Create both sides of the tile
        self.front_widget = QWidget()
        self.back_widget = QWidget()
        self.stacked_layout = QStackedLayout(self)

        self.setup_front_ui()
        self.setup_back_ui()

        # Add both sides to the stacked layout
        self.stacked_layout.addWidget(self.front_widget)
        self.stacked_layout.addWidget(self.back_widget)

        # Setup mouse click handling
        self.customContextMenuRequested.connect(self.show_context_menu)

        # Set initial styling
        self.setFixedHeight(200)
        self.setFixedWidth(287)
        self.setup_styles()

        # Add overlay if expired
        if self.is_expired:
            self.add_expired_overlay()

    def show_context_menu(self, position):  # 1 usage - Mewada,Madhusudan
        """
        right context menu for application tile
        :param position: (x,y) position of click(tuple)
        :return:
        """
        context_menu = QMenu(self)
        context_menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #88bbf7;
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #88bbf7;
                color: 88bbf7;
            }
        """)

        # Add menu actions
        flip_action = context_menu.addAction("Flip")

        # Show menu and handle selection
        action = context_menu.exec(self.mapToGlobal(position))
        if action == flip_action:
            self.flip_tile()

    def on_tile_clicked(self, event: QMouseEvent):  # Mewada,Madhusudan
        # handles flip context menu operation
        if event.button() == Qt.MouseButton.LeftButton:
            self.flip_tile()
            if self.is_expired and self.is_flipped is False:
                self.add_expired_overlay()

    def grey_it_out(self):  # 1 usage - Mewada,Madhusudan
        """
        this module resets all the application tile elements with greyish hue to implement Gray Overlay
        :return:
        """
        for widget in self.elements:
            widget.setDisabled(True)

        self.env_label.setStyleSheet(f"""
            background-color: #A9A9A9;
            color: white;
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: bold;
            font-family: Montserrat, serif;
        """)

        self.name_label.setStyleSheet(
            "font-weight: bold; font-size: 18px; color: #A9A9A9;font-family: Montserrat, serif;")  # A9A9A9  D3D3D3

        self.description_label.setStyleSheet("color: #A9A9A9; margin-bottom: 10px;font-family: Montserrat, serif;")

        self.status_label.setStyleSheet("""
            color: #A9A9A9;
            font-weight: bold;
            margin-top: 5px;
            font-family: Montserrat, serif;
        """)

        self.uninstall_button.setStyleSheet("""
            QPushButton {
                background-color: #10101060;
                color: white;
                border: none;
                padding: 8px 2px;
                border-radius: 5px;
                font-weight: bold;
                font-family: Montserrat, serif;
            }
        """)

        self.install_launch_button.setStyleSheet("""
            QPushButton {
                background-color: #10101060;
                color: white;
                border: none;
                padding: 8px 2px;
                border-radius: 5px;
                font-weight: bold;
                font-family: Montserrat, serif;
            }
        """)

    def setup_back_ui(self):  # 1 usage - Mewada,Madhusudan
        """
        This method creates the back/flipped layout for application tile with all elements added
        :return:
        """
        main_layout = QVBoxLayout(self.back_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # Style definitions
        container_style = """
            QWidget {
                background-color: #ffffff;
                padding: 17px;
            }
        """

        label_style = """
            QLabel {
                color: #666666;
                font-size: 9px;
            }
        """

        value_style = """
            QLabel {
                color: #2c3e50;
                font-size: 11px;
                font-weight: bold;
            }
        """

        expired_note_style = """
            QLabel {
                color: #e74c3c;
                font-size: 12px;
                border-radius: 5px;
                background-color: #fadbd8;
            }
        """

        # local scoped method to create detail containers
        def create_detail_container(title, value):  # Mewada,Madhusudan
            container = QWidget()
            container.setStyleSheet(container_style)
            container_layout = QVBoxLayout(container)
            container_layout.setSpacing(5)

            # Title
            title_label = QLabel(title)
            title_label.setStyleSheet(label_style)
            container_layout.addWidget(title_label)

            # Value
            value_label = QLabel(str(value))
            value_label.setStyleSheet(value_style)
            value_label.setWordWrap(True)
            container_layout.addWidget(value_label)

            return container

        # Add detail containers
        details = [
            ("IAHub ID", "Not Registered" if self.registration_id is np.nan else str(self.registration_id)),
            ("Release Date", str(pd.Timestamp(self.release_date))[:10]),
            ("Status", "Expired" if self.is_expired else "Active")
        ]

        for title, value in details:
            container = create_detail_container(title, value)
            main_layout.addWidget(container)

            # Conditional add expired note if status is 'Expired'
            if self.is_expired:
                note_container = QWidget()
                note_layout = QVBoxLayout(note_container)
                if self.registration_id is np.nan and self.environment == 'BETA':
                    expired_note = QLabel("⚠ Kindly register the application at IAHub portal.")
                else:
                    expired_note = QLabel(
                        "⚠ Application has expired. Contact Think_STO@restricted.chase.com for renewal.")
                expired_note.setStyleSheet(expired_note_style)
                expired_note.setWordWrap(True)
                expired_note.setAlignment(Qt.AlignmentFlag.AlignCenter)

                note_layout.addWidget(expired_note)
                main_layout.addWidget(note_container)

                # Add stretch to push everything to the top
                main_layout.addStretch()
            else:
                release_date = pd.Timestamp(self.release_date)
                expiry_date = release_date + timedelta(days=self.validity_period)
                container = create_detail_container("Validity", str(pd.Timestamp(expiry_date))[:10])
                main_layout.addWidget(container)

    def setup_front_ui(self):
        """Usage: Mewada,Madhusudan"""
        # This contains the original tile UI
        layout = QVBoxLayout(self.front_widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header layout with name and environment label
        header_layout = QHBoxLayout()
        self.name_label = QLabel(self.app_name)
        self.name_label.setStyleSheet(
            "font-weight: bold; font-size: 18px; color: #333;font-family: Montserrat, serif;")
        header_layout.addWidget(self.name_label)

        self.env_label = EnvironmentLabel(self.environment)
        header_layout.addWidget(self.env_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header_layout)

        # Description label
        self.description_label = QLabel(self.app_description.strip())
        self.description_label.setWordWrap(True)
        self.description_label.setFixedHeight(80)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.description_label.setStyleSheet("color: #666; margin-bottom: 10px;font-family: Montserrat, serif;")
        layout.addWidget(self.description_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.install_launch_button = QPushButton("Install")
        self.install_launch_button.clicked.connect(self.on_install_launch_clicked)
        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.setEnabled(True)
        self.uninstall_button.clicked.connect(self.on_uninstall_clicked)

        self.install_launch_button.setStyleSheet("""
                    QPushButton {
                        background-color: #00477b;
                        color: white;
                        border: none;
                        padding: 8px 2px;
                        border-radius: 5px;
                        font-weight: bold;
                        font-family: Montserrat, serif;
                    }
                    QPushButton:hover {
                        background-color: #2670a9;
                    }
                """)

        self.uninstall_button.setStyleSheet("""
                    QPushButton {
                        background-color: #c5c9d0;
                        color: white;
                        border: none;
                        padding: 8px 2px;
                        border-radius: 5px;
                        font-weight: bold;
                        font-family: Montserrat, serif;
                    }
                    QPushButton:hover {
                        background-color: #d9dde3;
                    }
                """)

        button_layout.addWidget(self.install_launch_button)
        button_layout.addWidget(self.uninstall_button)
        layout.addLayout(button_layout)

        # Status label
        self.status_label = QLabel("Not Installed")
        self.status_label.setStyleSheet("""
                    color: #6c757d;
                    font-weight: bold;
                    margin-top: 5px;
                    font-family: Montserrat, serif;
                """)
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #e0e0e0;
                        border-radius: 5px;
                        text-align: center;
                        background-color: #f8f9fa;
                        height: 10px;
                    }
                    QProgressBar::chunk {
                        background-color: #4a90e2;
                        border-radius: 5px;
                    }
                """)
        layout.addWidget(self.progress_bar)

        # Add tile hover effect
        self.setStyleSheet("""
                    ApplicationTile {
                        background-color: white;
                        border-radius: 10px;
                        border: 1px solid #e0e0e0;
                        font-family: Montserrat, serif;
                    }
                    ApplicationTile:hover {
                        border: 1px solid #4a90e2;
                        box-shadow: 0 4px 8px rgba(74, 144, 226, 0.1);
                    }
                """)

        # Update initial button states
        if self.is_app_installed(f'{self.install_path}.exe'):
            self.installed = True
            self.uninstall_button.setEnabled(True)
        self.update_button_states()

    def flip_tile(self):
        """2 usages - Mewada,Madhusudan"""
        # Animate the flip tile action
        self.is_flipped = not self.is_flipped
        self.stacked_layout.setCurrentIndex(1 if self.is_flipped else 0)

    def setup_styles(self):
        """1 usage - Mewada,Madhusudan"""
        # default empty tile stylesheet definition
        self.setStyleSheet("""
                    ApplicationTile {
                        background-color: white;
                        border-radius: 10px;
                        border: 1px solid #e0e0e0;
                        font-family: Montserrat, serif;
                    }
                    ApplicationTile:hover {
                        border: 1px solid #4a90e2;
                        box-shadow: 0 4px 8px rgba(74, 144, 226, 0.1);
                    }
                """)

    def add_expired_overlay(self):
        """2 usages - Mewada,Madhusudan"""
        # Method to be called for adding the overlay on application tile
        # :return:
        self.elements = [self.progress_bar, self.status_label, self.install_launch_button,
                         self.uninstall_button, self.description_label, self.name_label, self.env_label]
        # Create overlay widget
        self.overlay = QWidget(self)

        # Style the overlay
        self.overlay.setStyleSheet("""
                    background-color: rgba(0, 0, 0, 0.5);
                    border-radius: 10px;
                    backdrop-filter: blur(10px);
                """)

        # Ensure overlay covers the entire tile
        self.overlay.setGeometry(self.rect())
        self.overlay.show()

        # Disable all controls
        self.front_widget.setEnabled(False)
        self.grey_it_out()

        # Update the resize event to handle overlay positioning
        def resizeEvent(self, event):
            super().resizeEvent(event)
            if hasattr(self, 'overlay'):
                self.overlay.setGeometry(self.rect())

        # Add the resizeEvent method to the class
        self.resizeEvent = resizeEvent.__get__(self, type(self))

    def on_install_launch_clicked(self):
        """2 usages - Mewada,Madhusudan"""
        # Method with clauses to handle button status
        # :return:
        if self.update_available:
            self.update_application()
        elif not self.installed:
            self.install_application()
        else:
            self.launch_application()

    def is_app_installed(self, local_path):
        """3 usages - Mewada,Madhusudan"""
        # check app installation status
        return os.path.exists(local_path)

    def install_application(self):
        """2 usages - Mewada,Madhusudan"""
        # Method which calls thread for installation of solution
        # :return: None
        pslv_action_entry([{'SID': user_main, 'action': f'Installing {self.app_name}'}])
        self.progress_bar.setVisible(True)
        self.status_label.setText("Installing...")
        self.status_label.setStyleSheet("color: #7c92a6;font-family: Montserrat, serif;")

        # Create the installation directory if it doesn't exist
        os.makedirs(self.install_path, exist_ok=True)

        # Get the destination file path
        destination_file = os.path.join(self.install_path, f"{self.app_name}.exe")

        self.install_thread = InstallThread(self.shared_drive_path, destination_file)
        self.install_thread.progress.connect(self.update_progress)
        self.install_thread.finished.connect(self.installation_finished)
        self.install_thread.error.connect(self.installation_error)
        self.install_thread.start()

    def installation_error(self, error_message):
        """1 usage - Mewada,Madhusudan"""
        # Installation error handling method for thread
        # :param error_message: QMessageBox alert
        # :return:
        self.progress_bar.setVisible(False)
        self.status_label.setText("Installation Failed")
        self.status_label.setStyleSheet("color: red;")
        QMessageBox.critical(self, "Installation Error", f"Failed to install {self.app_name}: {error_message}")

    def update_progress(self, value):
        """1 usage - Mewada,Madhusudan"""
        self.progress_bar.setValue(value)

    def installation_finished(self):
        """1 usage - Mewada,Madhusudan"""
        # This method marks finish of solution installation process
        # :return: QMessageBox Info
        self.installed = True
        self.save_installed_version()  # Save version info after successful installation
        self.installed_version = self.version_number  # Update the installed version
        self.update_available = False  # Reset update flag after successful installation
        self.update_button_states()
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "Installation Complete",
                                f"{self.app_name} has been successfully installed.")

    def launch_application(self):
        """1 usage - Mewada,Madhusudan"""
        # Implementation of application launch logic here
        pslv_action_entry([{'SID': user_main, 'action': f'Launched {self.app_name}'}])
        executable_path = os.path.join(self.install_path, f"{self.app_name}.exe")
        release_date = pd.Timestamp(self.release_date)
        expiry_date = release_date + timedelta(days=self.validity_period)
        days_remaining = expiry_date - datetime.now()
        if os.path.exists(executable_path):
            try:
                if self.registration_id is np.nan and self.environment == 'BETA':
                    QMessageBox.warning(self, 'Action Required',
                                        f'Application is not registered at IA Hub and will stop working in {days_remaining.days} days.')
                    # Generate launch token before starting the application
                    LauncherSecurity.generate_launch_token(executable_path)
                    os.startfile(executable_path)
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Failed to launch application: {str(e)}')
        else:
            QMessageBox.warning(self, 'Error', f'Application executable not found at {executable_path}')

    def on_uninstall_clicked(self):
        """2 usages - Mewada,Madhusudan"""
        # Method to handle the uninstallation process for solution
        # :return: MessageBox Info
        if self.installed:
            try:
                shutil.rmtree(self.install_path)
                self.installed = False
                self.status_label.setText("Not Installed")
                self.status_label.setStyleSheet("""color: #6c757d;
                                                               font-weight: bold;
                                                               margin-top: 5px;
                                                               font-family: Montserrat, serif;""")
                self.install_launch_button.setText("Install")
                pslv_action_entry([{'SID': user_main, 'action': f'Uninstalled {self.app_name}'}])
                QMessageBox.information(self, 'Uninstall Complete',
                                        f'{self.app_name} has been successfully uninstalled.')
            except Exception as e:
                QMessageBox.warning(self, 'Uninstall Error', f'Failed to uninstall {self.app_name}: {str(e)}')

    def check_validity(self):
        """1 usage - Mewada,Madhusudan"""
        # Method to check validity of the solution for selected solution
        # :return: bool
        try:
            release_date = pd.Timestamp(self.release_date)
            expiry_date = release_date + timedelta(days=self.validity_period)
            return datetime.now() > expiry_date
        except Exception as e:
            print(f"Error checking validity: {str(e)}")
            return False

    def check_update_available(self):
        """1 usage - Mewada,Madhusudan"""
        # method which identifies solution needing update/has received updates
        # :return: bool
        try:
            installed_version = self.get_installed_version()
            if self.version_number and self.installed:
                if installed_version is None:
                    # If version file is missing but app is installed, assume it needs update
                    return True
                return float(self.version_number) > float(installed_version)
            return False
        except Exception as e:
            print(f"Error checking for updates: {str(e)}")
            return False

    def update_button_states(self):
        """4 usages - Mewada,Madhusudan"""
        # method which handles the visibility of install/update/launch button
        # :return: None
        if self.is_expired:
            self.status_label.setText("Application Expired" if self.environment == "PROD" else "UAT Period Expired")
            self.status_label.setStyleSheet("color: #dc3545; font-weight: bold;")
            self.install_launch_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            return
        if self.update_available:
            self.install_launch_button.setText("Update")
            self.status_label.setText("Update Available")
            self.status_label.setStyleSheet("color: #ff9800; font-weight: bold;")
        elif self.installed:
            self.install_launch_button.setText("Launch")
            self.status_label.setText("Ready for Launch")
            self.status_label.setStyleSheet("color: #7ec8ff; font-weight: bold;")
        else:
            self.install_launch_button.setText("Install")
            self.status_label.setText("Not Installed")
            self.status_label.setStyleSheet("color: #7c92a6; font-weight: bold;")

    def get_installed_version(self):  # 2 usages ± Mewada, Madhusudan
        """Read the installed version from a version file in the installation directory"""
        version_file = os.path.join(self.install_path, "version.txt")
        if os.path.exists(version_file):
            try:
                with open(version_file, 'r') as f:
                    return float(f.read().strip())
            except:
                return None
        return None

    def save_installed_version(self):  # 1 usage ± Mewada, Madhusudan
        """Save the current version number to a file after installation"""
        try:
            os.makedirs(self.install_path, exist_ok=True)
            version_file = os.path.join(self.install_path, "version.txt")
            with open(version_file, 'w') as f:
                f.write(str(self.version_number))
        except Exception as e:
            print(f"Error saving version info: {str(e)}")

    def update_application(self):  # 1 usage ± Mewada, Madhusudan
        """
        method checks for the new version availability
        :return:
        """
        latest_version = self.version_number
        if latest_version:
            try:
                if os.path.exists(self.install_path):
                    shutil.rmtree(self.install_path)

                self.shared_drive_path = self.shared_drive_path
                self.install_application()
                self.version_number = latest_version
                self.update_available = False
                self.update_button_states()

            except Exception as e:
                QMessageBox.critical(self, "Update Error", f"Failed to update {self.app_name}: {str(e)}")

    def create_button_layout(self):  # ± Mewada, Madhusudan
        # Buttons layout for application tile
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.install_launch_button = QPushButton("Install")
        self.install_launch_button.clicked.connect(self.on_install_launch_clicked)
        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.setEnabled(True)
        self.uninstall_button.clicked.connect(self.on_uninstall_clicked)

        self.install_launch_button.setStyleSheet("""
            QPushButton {
                background-color: #00477b;
                color: white;
                border: none;
                padding: 8px 2px;
                border-radius: 5px;
                font-weight: bold;
                font-family: Montserrat, serif;
            }
            QPushButton:hover {
                background-color: #2c70a9;
            }
        """)

        self.uninstall_button.setStyleSheet("""
            QPushButton {
                background-color: #c5c9d0;
                color: white;
                border: none;
                padding: 8px 2px;
                border-radius: 5px;
                font-weight: bold;
                font-family: Montserrat, serif;
            }
            QPushButton:hover {
                background-color: #d9de63;
            }
        """)

        button_layout.addWidget(self.install_launch_button)
        button_layout.addWidget(self.uninstall_button)
        return button_layout

    def setup_status_and_progress(self, layout):  # ± Mewada, Madhusudan
        # Status label
        self.status_label = QLabel("Not Installed")
        self.status_label.setStyleSheet("""
            color: #6c757d;
            font-weight: bold;
            margin-top: 5px;
        """)
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                text-align: center;
                background-color: #f8f9fa;
                height: 10px;
                font-family: Montserrat, serif;
            }
            QProgressBar::chunk {
                background-color: #4a90e2;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Add title hover effect
        self.setStyleSheet("""
            ApplicationTile {
                background-color: white;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
            }
            ApplicationTile:hover {
                border: 1px solid #4a90e2;
                box-shadow: 0 4px 8px rgba(74, 144, 226, 0.1);
            }
        """)

        # Update initial button states
        if self.is_app_installed(f'{self.install_path}.exe'):
            self.installed = True
            self.uninstall_button.setEnabled(True)
            self.update_button_states()


class NoAccessWidget(QWidget): # 2 usages ± Mewada, Madhusudan
    def __init__(self, is_gfbm_user): # ± Mewada, Madhusudan
        super().__init__()
        layout = QVBoxLayout(self)

        # Create a container for the message with styling
        message_container = QFrame()
        message_container.setObjectName("messageContainer")
        message_container.setStyleSheet("""
            #messageContainer {
                background-color: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                margin: 20px;
                font-family: Montserrat, serif;
            }
        """)

        container_layout = QVBoxLayout(message_container)

        icon_label = QLabel()
        icon_path = resource_path(f"resources/blocked.png")
        icon_pixmap = QPixmap(icon_path)
        if icon_pixmap.isNull():
            # Fallback text if icon isn't found
            icon_label.setText("⚠")
            icon_label.setStyleSheet("""
                QLabel {
                    font-size: 48px;
                    color: #6c757d;
                }
            """)
        else:
            icon_label.setPixmap(icon_pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(icon_label)

        message_label = QLabel("No Application Access")
        message_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #343a40;
                margin: 10px 0;
                font-family: Montserrat, serif;
            }
        """)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(message_label)

        description_label = QLabel(
            "Currently, you do not have access to any application.\n"
            "Please contact administrator for access permissions."
        )
        if not is_gfbm_user:
            description_label = QLabel(
                "Thanks for showing your interest for PSLV.\n"
                "At present, Application is accessible for Global Finance & Business Management India."
            )
        description_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                color: #6c757d;
                margin: 10px 0;
                font-family: Montserrat, serif;
            }
        """)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(description_label)

        # Add contact button
        contact_button = QPushButton("Help Center!!!")
        contact_button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                max-width: 200px;
                font-family: Montserrat, serif;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
        """)
        contact_button.clicked.connect(self.contact_admin)
        container_layout.addWidget(contact_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # Add everything to the main layout
        layout.addWidget(message_container, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def contact_admin(self): # 1 usage ± Mewada, Madhusudan
        # Open a support link in the default browser
        support_url = QUrl("https://confluence.prod.aws.jpmchase.net/confluence/spaces/GFITECH/pages/5228999093/APPLICATION+OWNER+AND+ADMINS")
        QDesktopServices.openUrl(support_url)


class MainWindow(QMainWindow): # 2 usages ± Mewada, Madhusudan
    """
    Main window class for pslv screen where all other components are merged
    FIXED VERSION: Added proper threading for all blocking operations
    """

    def __init__(self, df, cost_center, userdata): # ± Mewada, Madhusudan
        """
        default class method to initialize all required ui elements for MainWindow widget of PSLV
        :param df:
        """
        super().__init__()
        self.all_tiles = []
        self.access = df
        self.cost_center_df = cost_center
        self.userdata = userdata
        
        # Initialize worker threads
        self.refresh_worker = None
        self.admin_worker = None
        self.user_details_worker = None
        self.progress_dialog = None
        
        # Initialize user details and admin status
        self.user_details = DETAILS  # Default fallback
        self.cost_center = ""
        self.is_gfbm_user = False
        self.access_control_widget = QDialog()  # Default fallback
        
        # Set Windows username
        self.username = user_main
        self.setWindowTitle("PSLV by STD, GF&BM India")
        icon_path = resource_path(f"resources/STDJustLogo.PNG")
        self.setWindowIcon(QIcon(icon_path))
        self.setFixedSize(1200, 720)  # fixed window size#f5f6fa;
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f2f4f6;
                font-family: Montserrat, serif;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Setup UI components
        self.setup_ui(main_layout)
        
        # Start loading user details and admin check in background
        self.load_user_details_async()
        self.check_admin_privileges_async()

        # Load applications if data is available
        if len(self.access) != 0:
            self.load_applications()
        else:
            self.show_no_access_message()

    def setup_ui(self, main_layout):
        """Setup the main UI components"""
        # Sidebar Widget starts here
        sidebar = QWidget()
        sidebar.setFixedWidth(250)  # Set fixed width for sidebar#2c3e50
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #242526;
                color: white;
                font-family: Montserrat, serif;
            }
            QPushButton {
                background-color: #6c5ce7;
                color: white;
                border: none;
                padding: 10px;
                margin: 10px 5px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #5b4bc7;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)

        # Logo
        logo_label = QLabel()
        logo_path = resource_path(f"resources/gfbm.svg")
        logo_pixmap = QPixmap(logo_path)  # Replace with your logo path
        logo_label.setPixmap(logo_pixmap.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
        sidebar_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignRight)
        spacer = QSpacerItem(10, 50)
        sidebar_layout.addItem(spacer)

        # User details container (will be populated when data loads)
        self.user_details_container = QWidget()
        self.user_details_layout = QVBoxLayout(self.user_details_container)
        sidebar_layout.addWidget(self.user_details_container)

        sidebar_layout.addStretch()
        
        # Access control button (initially hidden)
        self.access_control_button = QPushButton("Access Management")
        self.access_control_button.setStyleSheet("""
            QPushButton {
                background-color: #2670A9;
                color: white;
                border: none;
                padding: 8px 2px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3380CD;
            }
        """)
        self.access_control_button.setVisible(False)  # Hide initially
        self.access_control_button.setCheckable(True)
        sidebar_layout.addWidget(self.access_control_button)

        exit_button = QPushButton("Exit")
        exit_button.setStyleSheet("""
            QPushButton {
                background-color: #A6150B;
                color: white;
                border: none;
                padding: 8px 2px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C42010;
            }
        """)
        exit_button.clicked.connect(self.close)
        sidebar_layout.addWidget(exit_button)

        # Main content area
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)

        # Logo
        logo_label = QLabel()
        logo_path = resource_path(f"resources/Full Logo.svg")
        logo_pixmap = QPixmap(logo_path)  # Replace with your logo path
        logo_label.setPixmap(logo_pixmap.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
        content_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignRight)

        # Applications title and search bar
        self.header_widget = QWidget()
        self.header_layout = QVBoxLayout(self.header_widget)

        # Create a custom widget for the search bar with icons
        self.search_widget = QWidget()
        self.search_layout = QHBoxLayout(self.search_widget)
        self.search_layout.setContentsMargins(15, 0, 15, 0)
        self.search_layout.setSpacing(10)
        # Search input
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search applications...")
        self.search_bar.textChanged.connect(self.filter_applications)
        self.search_bar.setStyleSheet("""
                    QLineEdit {
                        border: none;
                        padding: 12px 0px;
                        font-size: 14px;
                        background-color: transparent;
                    }
                    QLineEdit:focus {
                        outline: none;
                    }
                """)

        # Refresh button
        refresh_button = QPushButton("⟲")
        refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_button.setToolTip("⟲ Refresh Applications")
        refresh_button.clicked.connect(self.refresh_applications_async)  # FIXED: Use async version
        refresh_button.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: none;
                        color: #000000;
                        font-size: 20px;
                        padding: 5px;
                        min-width: 30px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        color: #4a90e2;
                    }
                """)

        # Add widgets to search layout
        self.search_layout.addWidget(self.search_bar)  # 1 is the stretch factor
        self.search_layout.addWidget(refresh_button)

        # Style the search widget container
        self.search_widget.setStyleSheet("""
                    QWidget {
                        border: 1px solid #ddd;
                        border-radius: 20px;
                        padding: 10px 15px;
                        font-size: 16px;
                        margin-bottom: 10px;
                        background-color: white;
                    }
                    QWidget:focus-within {
                        border-color: #4a90e2;
                        outline: none;
                    }
                """)

        # Scroll area for application grid or no access message
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
                    QScrollArea {
                        border: none;
                        background-color: transparent;
                    }
                    QScrollBar:vertical {
                        border: none;
                        background: #f0f0f0;
                        width: 8px;
                        border-radius: 4px;
                    }
                    QScrollBar::handle:vertical {
                        background: #c0c0c0;
                        border-radius: 4px;
                    }
                    QScrollBar::handle:vertical:hover {
                        background: #a0a0a0;
                    }
                """)
        scroll_content = QWidget()
        self.app_grid = QGridLayout(scroll_content)
        self.app_grid.setSpacing(20)
        scroll_area.setWidget(scroll_content)

        self.search_app = QWidget()
        self.search_app_layout = QVBoxLayout(self.search_app)
        self.search_app_layout.addWidget(self.header_widget)
        self.search_app_layout.addWidget(scroll_area)

        # Connect buttons to switch views
        self.access_control_button.clicked.connect(self.show_access_control)

        # Create stacked widget to switch between applications and access control
        self.stacked_widget = QStackedWidget()

        # Add widgets to stacked widget
        self.stacked_widget.addWidget(self.search_app)
        # Access control widget will be added when admin check completes

        main_layout.addWidget(sidebar)
        content_layout.addWidget(self.stacked_widget, stretch=1)
        main_layout.addWidget(content_area)
        self.stacked_widget.setCurrentIndex(0)

        # Add footer container
        footer_container = QWidget()
        footer_layout = QHBoxLayout(footer_container)
        footer_layout.setContentsMargins(0, 2, 0, 0)

        # Add version label
        version_label = QLabel("PSLV by STO v3.0")
        version_label.setStyleSheet("""
                    QLabel {
                        color: #595858;
                        font-size: 11px;
                        font-style: italic;
                    }
                """)

        # Add spacer to push version label to the right
        footer_layout.addStretch()
        footer_layout.addWidget(version_label)

        # Add footer to main layout
        content_layout.addWidget(footer_container)

    def show_progress_dialog(self, message):
        """Show progress dialog for long-running operations"""
        if self.progress_dialog is None:
            self.progress_dialog = QProgressDialog(message, "Cancel", 0, 0, self)
            self.progress_dialog.setWindowTitle("Loading...")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.canceled.connect(self.cancel_operations)
        else:
            self.progress_dialog.setLabelText(message)
        
        self.progress_dialog.show()

    def hide_progress_dialog(self):
        """Hide progress dialog"""
        if self.progress_dialog:
            self.progress_dialog.hide()

    def cancel_operations(self):
        """Cancel running operations"""
        if self.refresh_worker and self.refresh_worker.isRunning():
            self.refresh_worker.stop()
            self.refresh_worker.quit()
            self.refresh_worker.wait(3000)
        
        if self.admin_worker and self.admin_worker.isRunning():
            self.admin_worker.quit()
            self.admin_worker.wait(3000)
            
        if self.user_details_worker and self.user_details_worker.isRunning():
            self.user_details_worker.quit()
            self.user_details_worker.wait(3000)

    def load_user_details_async(self):
        """FIXED: Load user details in background thread"""
        self.user_details_worker = UserDetailsWorker(self.userdata)
        self.user_details_worker.user_details_loaded.connect(self.on_user_details_loaded)
        self.user_details_worker.error_occurred.connect(self.on_user_details_error)
        self.user_details_worker.start()

    def on_user_details_loaded(self, details, cost_center):
        """Handle user details loaded"""
        self.user_details = details
        self.cost_center = cost_center
        
        # Update UI with user details
        self.update_user_details_ui()
        
        # Check if user is GFBM user
        self.check_gfbm_user()

    def on_user_details_error(self, error_message):
        """Handle user details loading error"""
        print(f"Warning: {error_message}")
        # Use default details
        self.update_user_details_ui()

    def update_user_details_ui(self):
        """Update the UI with loaded user details"""
        # Clear existing details
        for i in reversed(range(self.user_details_layout.count())):
            self.user_details_layout.itemAt(i).widget().setParent(None)
        
        # Add new details
        for label, icon_name in self.user_details:
            detail_widget = self.create_detail_widget(label, icon_name)
            self.user_details_layout.addWidget(detail_widget)

    def check_admin_privileges_async(self):
        """FIXED: Check administrator privileges in background thread"""
        self.admin_worker = AdminCheckWorker()
        self.admin_worker.admin_check_complete.connect(self.on_admin_check_complete)
        self.admin_worker.error_occurred.connect(self.on_admin_check_error)
        self.admin_worker.start()

    def on_admin_check_complete(self, is_admin, managed_lob):
        """Handle admin check completion"""
        if is_admin:
            # Create access control widget
            self.access_control_widget = AccessControlDialog(self.username, managed_lob)
            self.stacked_widget.addWidget(self.access_control_widget)
            
            # Show access control button
            self.access_control_button.setVisible(True)

    def on_admin_check_error(self, error_message):
        """Handle admin check error"""
        print(f"Warning: {error_message}")
        # Keep button hidden and use default dialog

    def refresh_applications_async(self):
        """FIXED: Refresh applications in background thread"""
        if self.refresh_worker and self.refresh_worker.isRunning():
            return  # Already refreshing
        
        self.show_progress_dialog("Refreshing applications...")
        self.search_bar.clear()
        
        self.refresh_worker = RefreshWorker()
        self.refresh_worker.data_loaded.connect(self.on_refresh_complete)
        self.refresh_worker.error_occurred.connect(self.on_refresh_error)
        self.refresh_worker.progress_updated.connect(self.update_progress_message)
        self.refresh_worker.start()

    def on_refresh_complete(self, processed_df):
        """Handle refresh completion"""
        self.hide_progress_dialog()
        self.access = processed_df
        
        if len(self.access) > 0:
            self.load_applications()
            QMessageBox.information(self, "Application", "Refresh Complete...", QMessageBox.StandardButton.Ok)
        else:
            self.show_no_access_message()

    def on_refresh_error(self, error_message):
        """Handle refresh error"""
        self.hide_progress_dialog()
        QMessageBox.warning(self, "Refresh Error", error_message, QMessageBox.StandardButton.Ok)

    def update_progress_message(self, message):
        """Update progress dialog message"""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)

    def show_no_access_message(self):
        """Show no access message"""
        self.clear_layout(self.app_grid)
        self.app_grid.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        self.app_grid.addWidget(NoAccessWidget(self.is_gfbm_user))

    def check_gfbm_user(self):
        """Check if user is GFBM user"""
        if not self.cost_center_df.empty and self.cost_center:
            self.cost_center_df['cost_center_code'] = self.cost_center_df['cost_center_code'].astype(str)
            cc_column = self.cost_center_df['cost_center_code'].to_list()
            self.is_gfbm_user = self.cost_center in cc_column
        else:
            self.is_gfbm_user = False

    def show_access_control(self):
        """
        This method mainly controls UI element switch between applications and access control
        :return:
        """
        if self.stacked_widget.currentIndex() == 1:
            self.stacked_widget.setCurrentIndex(0)
            self.access_control_button.setText("Access Management")
            self.access_control_button.setStyleSheet("""
                        QPushButton {
                            background-color: #2670A9;
                            color: white;
                            border: none;
                            padding: 8px 2px;
                            border-radius: 5px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: #3380CD;
                        }
                    """)
        elif self.stacked_widget.currentIndex() == 0:
            self.stacked_widget.setCurrentIndex(1)
            self.access_control_button.setText("Applications")
            self.access_control_button.setStyleSheet("""
                        QPushButton {
                            background-color: #49A0AC;
                            color: white;
                            border: none;
                            padding: 8px 2px;
                            border-radius: 5px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: #49A0AC;
                        }
                    """)

    def create_detail_widget(self, value, icon_name):  # 1 usage = Mewada, Madhusudan
        """
        class method for creating combined similar ui objects for user details population based on the data coming
        from details
        :param value: string
        :param icon_name: string
        :return:
        """
        widget = QFrame()
        widget.setStyleSheet("QFrame { padding: 2px; }")

        layout = QHBoxLayout(widget)
        layout.setSpacing(5)
        layout.setContentsMargins(2, 2, 2, 2)

        icon_label = QLabel()
        icon_path = resource_path(f"resources/{icon_name}")
        icon = QIcon(icon_path)
        icon_label.setPixmap(icon.pixmap(25, 25))
        layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)

        text_label = QLabel(value)
        text_label.setFont(QFont('Helvetica', 10, QFont.Weight.DemiBold))
        text_label.setWordWrap(True)
        text_layout.addWidget(text_label)

        layout.addLayout(text_layout)
        layout.addStretch()
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        return widget

    def load_applications(self):  # 2 usages = Mewada, Madhusudan
        """
        the main cause method which list down the accessible application for the user
        :return:
        """
        try:
            self.clear_layout(self.app_grid)  # clear the space for Application files
            self.app_grid.setContentsMargins(10, 10, 10, 10)  # Add right margin to prevent cutoff

            if len(self.access) > 0:
                self.app_grid.setContentsMargins(10, 10, 10, 3)  # Add right margin to prevent cutoff

            self.app_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)  # Align to top-left
            self.all_tiles.clear()
            self.access['Expired'] = self.access.apply(lambda row: expire_sort(row), axis=1)
            self.access = self.access.sort_values(by=['Expired', 'Solution_Name'], ascending=[True, True])
            self.access.reset_index(inplace=True, drop=True)

            # loop over the list of available solution and create Application title
            for i, row in self.access.iterrows():
                title = ApplicationTile(
                    app_name=row['Solution_Name'],
                    app_description=row['Description'],
                    shared_drive_path=row['ApplicationExePath'],
                    environment=row['Status'],
                    release_date=row['Release_Date'],
                    validity_period=row['Validity_Period'],
                    version_number=float(row['Version_Number']) if row['Version_Number'] else 1.0,
                    registration_id=row['UMAT_IAHub_ID']
                )
                self.all_tiles.append(title)  # Store the tile reference

            # Initial layout of all tiles
            self.update_grid_layout("")
        except Exception as e:
            # You might want to show an error message to the user
            QMessageBox.critical(self, "Error", f"Failed to load applications: {str(e)}")

    def filter_applications(self, text):  # 1 usage = Mewada, Madhusudan
        self.update_grid_layout(text.lower())

    def update_grid_layout(self, filter_text):  # 2 usages = Mewada, Madhusudan
        # Clear the current layout
        self.clear_layout(self.app_grid)

        # Filter and layout visible tiles
        visible_tiles = [
            tile for tile in self.all_tiles
            if filter_text in tile.app_name.lower()
        ]

        # Add filtered tiles to the grid
        for i, title in enumerate(visible_tiles):
            row = i // 3  # 3 files per row
            col = i % 3
            self.app_grid.addWidget(title, row, col)
            title.setVisible(True)

        # Add stretch to bottom of grid to maintain alignment
        self.app_grid.setRowStretch(len(visible_tiles) // 3 + 1, stretch=1)

        self.adjust_layout_tiles(self.app_grid)

    def adjust_layout_tiles(self, layout):  # 1 usage = Mewada, Madhusudan
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and isinstance(item.widget(), ApplicationTile):
                item.widget()

    def clear_layout(self, layout):  # 3 usages = Mewada, Madhusudan
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)  # Remove widget

    def closeEvent(self, event):
        """Handle window close event - cleanup threads"""
        self.cancel_operations()
        event.accept()
