import ctypes
import os

import ujson as json


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def chong_boi_den_terminal():
    """
    Tat QuickEdit mode de tranh pause terminal khi click chuot.
    """
    if os.name != "nt":
        return

    try:
        kernel32 = ctypes.windll.kernel32
        std_input_handle = -10
        handle = kernel32.GetStdHandle(std_input_handle)

        enable_quick_edit_mode = 0x0040

        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        mode.value &= ~enable_quick_edit_mode
        kernel32.SetConsoleMode(handle, mode)
    except Exception:
        pass


def lay_vung_lam_viec():
    """
    Lay work area cua Windows de tranh de cua so de len taskbar.
    """
    user32 = ctypes.windll.user32

    try:
        spi_get_work_area = 48
        rect = RECT()
        if user32.SystemParametersInfoW(spi_get_work_area, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass

    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def tai_cau_hinh_ui():
    ui_cfg = {}
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            ui_cfg = config.get("terminal_ui", {})
    except Exception as e:
        print(f"Canh bao: Loi doc giao dien tu config: {e}. Dang dung mac dinh.")
    return ui_cfg


def move_window(hwnd, x, y, width, height):
    user32 = ctypes.windll.user32
    user32.MoveWindow(hwnd, int(x), int(y), int(width), int(height), True)


def dat_layout_ba_cot(hwnd, ui_cfg, role):
    """
    Layout theo 3 cot:
    - 2 cot ben trai cho workers
    - cot ben phai: master o tren, accountant o duoi
    """
    if role not in {"worker", "master", "accountant"}:
        return False

    left, top, screen_width, screen_height = lay_vung_lam_viec()

    offset_x = ui_cfg.get("offset_x", 10)
    offset_y = ui_cfg.get("offset_y", 0)
    gap_x = ui_cfg.get("gap_x", 10)
    gap_y = ui_cfg.get("gap_y", 10)

    usable_width = max(600, screen_width - (offset_x * 2) - (gap_x * 2))
    usable_height = max(400, screen_height - (offset_y * 2))
    col_width = max(220, usable_width // 3)

    x0 = left + offset_x
    x1 = x0 + col_width + gap_x
    x2 = x1 + col_width + gap_x
    top_y = top + offset_y

    if role == "worker":
        worker_index_env = os.environ.get("MATRIX_WORKER_INDEX", "0")
        worker_count_env = os.environ.get("MATRIX_WORKER_COUNT", "1")
        try:
            worker_index = max(0, int(worker_index_env))
        except ValueError:
            worker_index = 0
        try:
            worker_count = max(1, int(worker_count_env))
        except ValueError:
            worker_count = 1

        worker_columns = 2
        worker_rows = max(1, (worker_count + worker_columns - 1) // worker_columns)
        worker_height = max(140, (usable_height - ((worker_rows - 1) * gap_y)) // worker_rows)

        worker_col = worker_index % worker_columns
        worker_row = worker_index // worker_columns
        x = x0 if worker_col == 0 else x1
        y = top_y + worker_row * (worker_height + gap_y)
        move_window(hwnd, x, y, col_width, worker_height)
        return True

    panel_height = max(180, (usable_height - gap_y) // 2)
    x = x2
    y = top_y if role == "master" else top_y + panel_height + gap_y
    move_window(hwnd, x, y, col_width, panel_height)
    return True


def dat_layout_mac_dinh(hwnd, ui_cfg, slot):
    chieu_rong = ui_cfg.get("width", 1000)
    chieu_cao = ui_cfg.get("height", 250)
    toa_do_x = ui_cfg.get("offset_x", 10)
    offset_y = ui_cfg.get("offset_y", 0)
    gap_x = ui_cfg.get("gap_x", 10)
    gap_y = ui_cfg.get("gap_y", 10)
    so_cot = ui_cfg.get("columns", 0)

    left, top, screen_width, _screen_height = lay_vung_lam_viec()
    buoc_x = max(1, chieu_rong + gap_x)
    buoc_y = max(1, chieu_cao + gap_y)

    if so_cot <= 0:
        kha_dung = max(chieu_rong, screen_width - toa_do_x)
        so_cot = max(1, kha_dung // buoc_x)

    slot_index = max(1, slot) - 1
    cot = slot_index % so_cot
    hang = slot_index // so_cot

    x = left + toa_do_x + cot * buoc_x
    y = top + offset_y + hang * buoc_y
    move_window(hwnd, x, y, chieu_rong, chieu_cao)


def dan_tran_cua_so(vi_tri_hang):
    """
    Dat cua so terminal vao mot slot tren man hinh.
    Neu co bien moi truong MATRIX_WINDOW_SLOT thi uu tien dung slot do.
    """
    chong_boi_den_terminal()

    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if not hwnd:
        return

    ui_cfg = tai_cau_hinh_ui()
    slot_env = os.environ.get("MATRIX_WINDOW_SLOT")
    try:
        slot = int(slot_env) if slot_env else int(vi_tri_hang)
    except (TypeError, ValueError):
        slot = int(vi_tri_hang)

    layout_mode = os.environ.get("MATRIX_WINDOW_LAYOUT", ui_cfg.get("layout_mode", "grid"))
    role = os.environ.get("MATRIX_WINDOW_ROLE", "")

    if layout_mode == "three_panel" and dat_layout_ba_cot(hwnd, ui_cfg, role):
        return

    dat_layout_mac_dinh(hwnd, ui_cfg, slot)
