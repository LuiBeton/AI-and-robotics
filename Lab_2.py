import sounddevice as sd
import queue
import json
import time
import re

from vosk import Model, KaldiRecognizer
import pydobot


# =========================================================
# НАЛАШТУВАННЯ
# =========================================================

MODEL_PATH = "vosk-model-uk-v3-lgraph"
PORT = "COM4"

VOSK_RATE = 16000
BLOCKSIZE = 8000  # ~0.5 сек при 16kHz

MOVE_STEP = 20  # мм


# Межі
MIN_X = 220
MAX_X = 330
MIN_Y = -130
MAX_Y = 130
MIN_Z = -54
MAX_Z = 100

# Кубик
TABLE_Z = -54
CUBE_HEIGHT = 10
SUCTION_OFFSET = 2
PICK_R = 0

# Перенесення вправо
TRANSFER_Y = 50


# =========================================================
# ДОПОМІЖНІ
# =========================================================

def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("ґ", "г")
    text = re.sub(r"[^а-яіїєa-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def safe_suck_off(device):
    try:
        device.suck(False)
        print("Присоску (насос) вимкнено.")
    except Exception as e:
        print(f"Не вдалося вимкнути присоску: {e}")


def get_position(device):
    x, y, z, r, *_ = device.pose()
    print(f"Поточна позиція: X={x:.1f}, Y={y:.1f}, Z={z:.1f}, R={r:.1f}")
    return x, y, z, r


def check_position(x, y, z):
    if x < MIN_X or x > MAX_X:
        print("ПОМИЛКА: X виходить за межі!")
        return False
    if y < MIN_Y or y > MAX_Y:
        print("ПОМИЛКА: Y виходить за межі!")
        return False
    if z < MIN_Z or z > MAX_Z:
        print("ПОМИЛКА: Z виходить за межі!")
        return False
    return True


def move_robot(device, x, y, z, r):
    if not check_position(x, y, z):
        print("Рух скасовано.")
        return False
    device.move_to(x, y, z, r, wait=True)
    return True


# =========================================================
# РУХИ
# =========================================================

def move_up(device):
    x, y, z, r = get_position(device)
    move_robot(device, x, y, z + MOVE_STEP, r)


def move_down(device):
    x, y, z, r = get_position(device)
    move_robot(device, x, y, z - MOVE_STEP, r)


def move_right(device):
    x, y, z, r = get_position(device)
    move_robot(device, x, y + MOVE_STEP, z, r)


def move_left(device):
    x, y, z, r = get_position(device)
    move_robot(device, x, y - MOVE_STEP, z, r)


def move_forward(device):
    x, y, z, r = get_position(device)
    move_robot(device, x + MOVE_STEP, y, z, r)


def move_backward(device):
    x, y, z, r = get_position(device)
    move_robot(device, x - MOVE_STEP, y, z, r)


def pick_object(device):
    print("\n========== ВЗЯТТЯ КУБИКА ==========")
    x, y, current_z, _ = get_position(device)

    cube_top_z = TABLE_Z + CUBE_HEIGHT
    target_z = cube_top_z + SUCTION_OFFSET

    if not check_position(x, y, target_z):
        print("Неможливо опуститися до кубика.")
        return False

    if not move_robot(device, x, y, target_z, PICK_R):
        return False

    print("Вмикаємо присоску...")
    device.suck(True)
    time.sleep(1)

    if not move_robot(device, x, y, current_z, PICK_R):
        return False

    print("Кубик взято!")
    return True


def transfer_right(device):
    print("\n========== ПЕРЕНЕСЕННЯ ==========")
    x, y, current_z, _ = get_position(device)

    cube_top_z = TABLE_Z + CUBE_HEIGHT
    target_z = cube_top_z + SUCTION_OFFSET

    try:
        if not move_robot(device, x, y, target_z, PICK_R):
            return False

        device.suck(True)
        time.sleep(1)

        if not move_robot(device, x, y, current_z, PICK_R):
            return False

        new_y = y + TRANSFER_Y
        if not check_position(x, new_y, current_z):
            print("Переміщення вправо неможливе!")
            return False

        if not move_robot(device, x, new_y, current_z, PICK_R):
            return False

        if not move_robot(device, x, new_y, target_z, PICK_R):
            return False

        safe_suck_off(device)
        time.sleep(0.5)

        if not move_robot(device, x, new_y, current_z, PICK_R):
            return False

        print("Кубик успішно перенесено!")
        return True

    finally:
        safe_suck_off(device)


def go_home(device):
    print("Повернення в початкове положення...")
    device.home()
    print("DOBOT вдома.")


# =========================================================
# КОМАНДИ
# =========================================================

def process_command(text, device):
    text = normalize_text(text)
    print(f"\nРозпізнано final: {text}")

    up_words = ["вверх", "вгору", "угору", "вище", "підніми", "підняти"]
    down_words = ["вниз", "униз", "нижче", "опусти", "опустити"]
    right_words = ["вправо", "праворуч", "право"]
    left_words = ["вліво", "ліворуч", "ліво"]
    forward_words = ["вперед", "прямо"]
    backward_words = ["назад"]
    pick_words = ["візьми", "взяти", "захопи"]
    transfer_words = ["перенеси", "перемісти", "переклади"]
    release_words = ["відпусти", "відпустити", "вимкни присоску", "вимкни насос"]
    suck_on_words = ["присоска", "увімкни присоску", "увімкни насос"]
    home_words = ["додому", "домой", "home", "на базу"]

    if any(w in text for w in up_words):
        move_up(device)
    elif any(w in text for w in down_words):
        move_down(device)
    elif any(w in text for w in right_words):
        move_right(device)
    elif any(w in text for w in left_words):
        move_left(device)
    elif any(w in text for w in forward_words):
        move_forward(device)
    elif any(w in text for w in backward_words):
        move_backward(device)
    elif any(w in text for w in pick_words):
        pick_object(device)
    elif any(w in text for w in transfer_words):
        transfer_right(device)
    elif any(w in text for w in release_words):
        safe_suck_off(device)
    elif any(w in text for w in suck_on_words):
        device.suck(True)
        print("Присоску увімкнено.")
    elif any(w in text for w in home_words):
        go_home(device)
    else:
        print("Команда не розпізнана.")


# =========================================================
# MAIN STREAM
# =========================================================

def main():
    print("======================================")
    print(" VOSK + DOBOT MAGICIAN LITE (STREAM)")
    print("======================================")

    print("\nЗавантаження Vosk...")
    model = Model(MODEL_PATH)

    # Обмежуємо словник командами (краще для точності)
    grammar = [
        "вгору", "вверх", "вниз", "вправо", "вліво", "вперед", "назад",
        "візьми", "взяти", "захопи", "перенеси", "перемісти", "переклади",
        "відпусти", "вимкни присоску", "вимкни насос",
        "увімкни присоску", "увімкни насос", "присоска",
        "додому", "на базу", "[unk]"
    ]
    rec = KaldiRecognizer(model, VOSK_RATE, json.dumps(grammar, ensure_ascii=False))
    rec.SetWords(True)

    print("Vosk завантажено.")

    print("\nПідключення до DOBOT...")
    device = pydobot.Dobot(port=PORT, verbose=False)
    print("DOBOT підключений!")

    print("\nСистема готова. Натисни Ctrl+C для виходу.")

    q = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"⚠️ Audio status: {status}")
        q.put(bytes(indata))

    try:
        with sd.RawInputStream(
            samplerate=VOSK_RATE,
            blocksize=BLOCKSIZE,
            dtype="int16",
            channels=1,
            callback=audio_callback
        ):
            print("\n🎤 Слухаю... говори команду")
            last_partial = ""

            while True:
                data = q.get()

                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    final_text_raw = result.get("text", "").strip()

                    if final_text_raw:
                        print(f"\n📝 final(raw): {final_text_raw}")
                        process_command(final_text_raw, device)
                    else:
                        print("\n(порожній final)")
                    last_partial = ""
                else:
                    p = json.loads(rec.PartialResult()).get("partial", "").strip()
                    if p and p != last_partial:
                        print(f"… partial: {p}")
                        last_partial = p

    except KeyboardInterrupt:
        print("\nПрограму зупинено (Ctrl+C).")
    except Exception as e:
        print(f"\nПомилка: {e}")
    finally:
        safe_suck_off(device)
        try:
            device.close()
            print("З'єднання з DOBOT закрито.")
        except Exception as e:
            print(f"Не вдалося коректно закрити з'єднання: {e}")


if __name__ == "__main__":
    main()