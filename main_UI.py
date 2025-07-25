from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QFileDialog, QHBoxLayout, QVBoxLayout, QTextEdit, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter, QSizePolicy, QFrame, QTreeWidgetItem
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

        self.btn_browse = QPushButton("Open Folder")
        self.btn_browse.setIcon(QIcon.fromTheme("folder"))
        # self.btn_browse.setFixedSize(32, 32)
        self.btn_browse.clicked.connect(self.choose_folder)

        self.lbl_folder = QLabel("Chưa chọn thư mục")
        self.lbl_folder.setStyleSheet("font-weight: bold; color: #FFFFFF; background-color: #333333; padding: 5px;")
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
        # Tab Layout cho Prompt
        from PyQt5.QtWidgets import QTabWidget, QTreeWidget, QTreeWidgetItem
        self.tab_prompt = QTabWidget()
        self.tab_prompt.setMinimumWidth(300)

        # Tab Content (chỉ đọc metadata)
        self.tab_content = QWidget()
        content_layout = QVBoxLayout()
        self.tab_content.setLayout(content_layout)
        self.tree_metadata = QTreeWidget()
        self.tree_metadata.setHeaderLabels(["Keyword", "Content"])
        self.tree_metadata.setColumnCount(2)
        self.tree_metadata.setRootIsDecorated(False)
        self.tree_metadata.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.tree_metadata.setWordWrap(True)
        content_layout.addWidget(self.tree_metadata)

        # Tab Edit (giữ layout cũ)
        self.tab_edit = QWidget()
        edit_layout = QVBoxLayout()
        self.tab_edit.setLayout(edit_layout)
        self.txt_positive = QTextEdit()
        self.txt_positive.setPlaceholderText("Positive Prompt (e.g. masterpiece, 8k, detailed)")
        self.txt_negative = QTextEdit()
        self.txt_negative.setPlaceholderText("Negative Prompt (e.g. low quality, blurry)")
        self.chk_autosave = QCheckBox("Auto Save")
        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_prompt_file)
        edit_layout.addWidget(self.txt_positive)
        edit_layout.addWidget(self.txt_negative)
        edit_layout.addWidget(self.chk_autosave)
        edit_layout.addWidget(self.btn_save)

        self.tab_prompt.addTab(self.tab_content, "Content")
        self.tab_prompt.addTab(self.tab_edit, "Edit")

        # Thêm vào splitter
        self.main_splitter.addWidget(image_widget)
        self.main_splitter.addWidget(self.tab_prompt)
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
        self.load_metadata_content(image_path)

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
                content = f.read().strip()
                # Nếu đúng format cũ: <positive>###<negative>###size
                parts = content.split("###")
                if len(parts) >= 2:
                    self.txt_positive.setText(parts[0])
                    self.txt_negative.setText(parts[1])
        elif os.path.exists(image_path):
            from PIL import Image
            import PIL
            meta_text = None
            try:
                img = Image.open(image_path)
                info = img.info
                # PNG: metadata thường nằm trong info['parameters'] hoặc info['Description'] hoặc info['prompt']
                for k in ['parameters', 'Description', 'prompt', 'Comment', 'Software']:
                    if k in info and isinstance(info[k], str) and len(info[k]) > 10:
                        meta_text = info[k]
                        break
                # JPEG: metadata có thể nằm trong EXIF (UserComment, ImageDescription...)
                if meta_text is None and hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    if exif:
                        for tag, value in exif.items():
                            decoded = PIL.ExifTags.TAGS.get(tag, tag)
                            if decoded in ['UserComment', 'ImageDescription', 'XPComment', 'XPSubject'] and isinstance(value, str) and len(value) > 10:
                                meta_text = value
                                break
            except Exception as e:
                meta_text = None
            # Nếu không đúng format, tìm positive/negative prompt trong metadata
            meta = self.parse_metadata(meta_text) if meta_text else {}
            self.txt_positive.setText(meta.get("Positive prompt", ""))
            self.txt_negative.setText(meta.get("Negative prompt", ""))
        else:
            self.txt_positive.clear()
            self.txt_negative.clear()

    def load_metadata_content(self, image_path):
        # Đọc metadata trực tiếp từ file ảnh (PNG/JPG)
        from PIL import Image
        import PIL
        import textwrap
        self.tree_metadata.clear()
        meta_text = None
        try:
            img = Image.open(image_path)
            info = img.info
            # PNG: metadata thường nằm trong info['parameters'] hoặc info['Description'] hoặc info['prompt']
            for k in ['parameters', 'Description', 'prompt', 'Comment', 'Software']:
                if k in info and isinstance(info[k], str) and len(info[k]) > 10:
                    meta_text = info[k]
                    break
            # JPEG: metadata có thể nằm trong EXIF (UserComment, ImageDescription...)
            if meta_text is None and hasattr(img, '_getexif') and img._getexif():
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        decoded = PIL.ExifTags.TAGS.get(tag, tag)
                        if decoded in ['UserComment', 'ImageDescription', 'XPComment', 'XPSubject'] and isinstance(value, str) and len(value) > 10:
                            meta_text = value
                            break
        except Exception as e:
            meta_text = None
        if not meta_text:
            # Không có metadata
            return
        meta = self.parse_metadata(meta_text)
        wrap_len = 80  # Số ký tự tối đa mỗi dòng
        for key in [
            "Positive prompt", "Negative prompt", "Steps", "Sampler", "Schedule type", "CFG scale", "Seed", "Face restoration", "Size", "Model hash", "Model", "Clip skip", "Token merging ratio", "Lora hash", "Other", "Version"]:
            val = meta.get(key, "")
            if val:
                # Tự động wrapped nếu quá dài
                if isinstance(val, str) and len(val) > wrap_len:
                    val = '\n'.join(textwrap.wrap(val, wrap_len))
                item = QTreeWidgetItem([key, val])
                self.tree_metadata.addTopLevelItem(item)

    def parse_metadata(self, content):
        # Tách positive/negative prompt
        meta = {}
        pos = ""
        neg = ""
        other = {}
        lines = content.splitlines()
        text = content
        # Tìm vị trí Negative prompt:
        idx = text.find("Negative prompt:")
        if idx != -1:
            pos = text[:idx].strip()
            rest = text[idx:]
            # Tìm các key
            keys = [
                "Negative prompt:", "Steps:", "Sampler:", "Schedule type:", "CFG scale:", "Seed:", "Face restoration:", "Size:", "Model hash:", "Model:", "Clip skip:", "Token merging ratio:", "Lora hash:", "Version:", "ControlNet 0:"]
            for k in keys:
                kidx = rest.find(k)
                if kidx != -1:
                    val_start = kidx + len(k)
                    # Tìm kết thúc
                    next_idx = len(rest)
                    for k2 in keys:
                        if k2 == k:
                            continue
                        k2idx = rest.find(k2, val_start)
                        if k2idx != -1 and k2idx < next_idx:
                            next_idx = k2idx
                    val = rest[val_start:next_idx].strip().strip(",")
                    key_name = k.replace(":", "").strip()
                    if k == "Negative prompt:":
                        neg = val
                    else:
                        meta[key_name] = val
            meta["Positive prompt"] = pos
            meta["Negative prompt"] = neg
            # Tìm các nội dung dư
            known_keys = [k.replace(":", "").strip() for k in keys]
            # Lấy các phần còn lại
            import re
            for m in re.finditer(r"(\w[\w ]*):", rest):
                k = m.group(1).strip()
                if k not in known_keys:
                    # Lấy value
                    start = m.end()
                    end = rest.find("\n", start)
                    if end == -1:
                        end = len(rest)
                    val = rest[start:end].strip().strip(",")
                    other[k] = val
            if other:
                meta["Other"] = str(other)
        else:
            # Không có Negative prompt, lấy hết làm Positive
            meta["Positive prompt"] = text.strip()
            meta["Negative prompt"] = ""
        return meta

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