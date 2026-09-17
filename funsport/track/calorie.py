"""官方卡路里/功率公式。"""


def official_kcal(weight, total_time, total_dis):
    km = total_dis / 1000.0
    if km <= 0:
        met = 12.0
    else:
        pace = (total_time / 60.0) / km
        if pace < 10.0:
            met = 33.0 / pace + 4.1
        elif pace < 12.0:
            met = 102.0 / pace - 3.7
        else:
            met = 33.6 / pace + 1.0
    met = round(met * 10) / 10
    return int(round(weight * met * (total_time / 3600.0)))


def avg_power(weight, total_dis, total_time):
    if total_time <= 0:
        return 0
    return int(round(1.1 * weight * (total_dis / total_time)))
