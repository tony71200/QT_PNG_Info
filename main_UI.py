from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QFileDialog, QHBoxLayout, QVBoxLayout, QTextEdit, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter, QSizePolicy, QFrame
)
from PyQt5.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent
from PyQt5.QtCore import Qt, QSize
import sys
import os
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

class ImageDropLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.image_dropped_callback = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        image_paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and any(path.lower().endswith(ext) for ext in image_extensions):
                image_paths.append(path)
        if image_paths and self.image_dropped_callback:
            self.image_dropped_callback(image_paths)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Prompt Manager")
        self.setGeometry(100, 100, 1000, 700)

        self.folder_path = ""
        self.current_image_path = ""

        self.init_ui()
        self.statusBar().showMessage("Ready")

    def init_ui(self):
        # Widget trung tâm
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # Layout chính
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Layout cho thanh chọn thư mục
        folder_layout = QHBoxLayout()

        self.btn_browse = QPushButton()
        self.btn_browse.setIcon(QIcon.fromTheme("folder"))
        self.btn_browse.setFixedSize(32, 32)
        self.btn_browse.clicked.connect(self.choose_folder)

        self.lbl_folder = QLabel("Chưa chọn thư mục")
        self.lbl_folder.setStyleSheet("font-weight: bold; color: #555")
        self.lbl_folder.setTextInteractionFlags(Qt.TextSelectableByMouse)

        folder_layout.addWidget(self.btn_browse)
        folder_layout.addWidget(self.lbl_folder)

        # Split panel chính chia làm 2: Trái (ảnh) - Phải (prompt)
        self.main_splitter = QSplitter(Qt.Horizontal)

        # ----- KHU HÌNH ẢNH (TRÁI) -----
        image_widget = QWidget()
        image_layout = QVBoxLayout()
        image_widget.setLayout(image_layout)
        image_widget.setMinimumWidth(400)

        self.lbl_image = ImageDropLabel("Kéo ảnh vào đây hoặc chọn từ danh sách")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setFrameShape(QFrame.Box)
        self.lbl_image.setMinimumHeight(400)
        self.lbl_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_image.image_dropped_callback = self.handle_dropped_images

        self.list_images = QListWidget()
        self.list_images.setFixedHeight(150)
        self.list_images.setViewMode(QListWidget.IconMode)
        self.list_images.setIconSize(QSize(100, 100))
        self.list_images.setResizeMode(QListWidget.Adjust)
        self.list_images.setMovement(QListWidget.Static)
        self.list_images.itemClicked.connect(self.display_selected_image)

        image_layout.addWidget(self.lbl_image)
        image_layout.addWidget(self.list_images)

        # ----- KHU PROMPT (PHẢI) -----
        prompt_widget = QWidget()
        prompt_layout = QVBoxLayout()
        prompt_widget.setLayout(prompt_layout)
        prompt_widget.setMinimumWidth(300)

        self.txt_positive = QTextEdit()
        self.txt_positive.setPlaceholderText("Positive Prompt (e.g. masterpiece, 8k, detailed)")

        self.txt_negative = QTextEdit()
        self.txt_negative.setPlaceholderText("Negative Prompt (e.g. low quality, blurry)")

        self.chk_autosave = QCheckBox("Auto Save")
        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_prompt_file)

        prompt_layout.addWidget(self.txt_positive)
        prompt_layout.addWidget(self.txt_negative)
        prompt_layout.addWidget(self.chk_autosave)
        prompt_layout.addWidget(self.btn_save)

        # Thêm vào splitter
        self.main_splitter.addWidget(image_widget)
        self.main_splitter.addWidget(prompt_widget)
        self.main_splitter.setSizes([600, 400])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)

        # Đặt tỉ lệ cho layout
        main_layout.addLayout(folder_layout, 0)
        main_layout.addWidget(self.main_splitter, 1)

    def choose_folder(self):
        initial_dir = self.folder_path if os.path.isdir(self.folder_path) else os.getcwd()
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa ảnh", initial_dir)
        if folder:
            self.folder_path = folder
            self.lbl_folder.setText(folder)
            self.load_images_from_folder(folder)

    def load_images_from_folder(self, folder):
        self.list_images.clear()
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']

        image_files = [f for f in os.listdir(folder) if any(f.lower().endswith(ext) for ext in image_extensions)]
        image_files.sort()

        for file in image_files:
            full_path = os.path.join(folder, file)
            icon = QIcon(full_path)
            item = QListWidgetItem(icon, file)
            item.setData(Qt.UserRole, full_path)
            self.list_images.addItem(item)

        if self.list_images.count() > 0:
            self.list_images.setCurrentRow(0)
            self.display_selected_image(self.list_images.item(0))

    def display_selected_image(self, item):
        if self.chk_autosave.isChecked():
            self.save_prompt_file()

        image_path = item.data(Qt.UserRole)
        self.display_image_from_path(image_path)
        self.load_prompt_file(image_path)

    def display_image_from_path(self, path):
        self.current_image_path = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(self.lbl_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_image.setPixmap(scaled)
            self.statusBar().showMessage(path)
        else:
            self.lbl_image.setText("Không thể hiển thị ảnh")
            self.statusBar().showMessage("Không thể hiển thị ảnh")

    def load_prompt_file(self, image_path):
        prompt_path = os.path.splitext(image_path)[0] + ".txt"
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                parts = f.read().strip().split("###")
                self.txt_positive.setText(parts[0] if len(parts) > 0 else "")
                self.txt_negative.setText(parts[1] if len(parts) > 1 else "")
        else:
            self.txt_positive.clear()
            self.txt_negative.clear()

    def save_prompt_file(self):
        if not self.current_image_path:
            return

        positive = self.txt_positive.toPlainText().strip().split("\n")
        positive = " ".join(positive)
        negative = self.txt_negative.toPlainText().strip().split("\n")
        negative = " ".join(negative)

        image = QPixmap(self.current_image_path)
        w, h = image.width(), image.height()
        if w > h:
            size_str = "1216x832"
        elif h > w:
            size_str = "832x1216"
        else:
            size_str = "1024x1024"

        if not positive:
            positive = "1boy, 1 man"

        if not negative:
            negative = "(1girl, woman, female)"

        content = f"{positive}###{negative}###{size_str}"
        prompt_path = os.path.splitext(self.current_image_path)[0] + ".txt"

        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(content)

    def handle_dropped_images(self, image_paths):
        if not image_paths:
            return

        # Cập nhật folder_path và label
        folder = os.path.dirname(image_paths[0])
        self.folder_path = folder
        self.lbl_folder.setText(folder)

        # Lưu danh sách ảnh vào thư mục đó (không trùng)
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        all_images = sorted([f for f in os.listdir(folder) if any(f.lower().endswith(ext) for ext in image_extensions)])

        self.list_images.clear()
        for file in all_images:
            full_path = os.path.join(folder, file)
            icon = QIcon(full_path)
            item = QListWidgetItem(icon, file)
            item.setData(Qt.UserRole, full_path)
            self.list_images.addItem(item)

        # Hiển thị ảnh đầu tiên trong danh sách kéo vào
        self.list_images.setCurrentRow(0)
        self.display_image_from_path(image_paths[0])
        self.load_prompt_file(image_paths[0])

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_D):
            self.navigate_image(1)
        elif key in (Qt.Key_Left, Qt.Key_A):
            self.navigate_image(-1)

    def navigate_image(self, step):
        current_row = self.list_images.currentRow()
        total = self.list_images.count()
        next_row = (current_row + step) % total
        self.list_images.setCurrentRow(next_row)
        item = self.list_images.item(next_row)
        if item:
            self.display_selected_image(item)

    


if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        with open("ElegantDark.qss", "r") as f:
            app.setStyleSheet(f.read())
    except:
        pass
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())