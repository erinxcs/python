# Face Sorter

Automatic na pag-sort ng photos ayon sa mukha (InsightFace buffalo_l, offline, CPU).

## Resulta
Gagawa ng folder na `<photos folder>_Sorted` katabi ng photos mo:

| Folder | Laman |
|---|---|
| `Face_1`, `Face_2`, ... | Photos na iisang mukha lang. `Face_1` = pinakamaraming photos |
| `Group_Photos` | Photos na may 2+ mukha (hindi dinu-duplicate) |
| `Unknown` | Walang mukha, malabo, o mukhang isang beses lang lumabas |

Kasama ang lahat ng subfolders. **Move** ito, kaya mawawala ang photos sa original na pwesto, pero may `--undo`.

## Setup (Windows, isang beses lang)
1. I-install ang **Python 3.10 pataas** (python.org). I-check ang **"Add Python to PATH"**.
2. I-double-click ang **`run.bat`**. Kapag kulang ang libraries, tatanungin ka kung i-install na (kailangan ng internet).
   - O manual: buksan ang Command Prompt dito at i-run `pip install -r requirements.txt`
   - Hindi na kailangan ang Microsoft C++ Build Tools (insightface 2.x ay may handang wheel na).
3. Sa unang run, magda-download ito ng model (~300MB). Pagkatapos noon, offline na.

## Paggamit
```
python face_sorter.py "C:\Users\Ako\Pictures\Photos" --dry-run
```
Silip muna ito: walang ililipat, pero gagawa ng `_preview.csv` para makita mo ang plano.

Kapag okay na, alisin ang `--dry-run`:
```
python face_sorter.py "C:\Users\Ako\Pictures\Photos"
```
Pwede ring i-double-click ang `run.bat`: i-paste ang folder path, tapos pumili sa menu (silip, sort, undo, threshold).

Para ibalik lahat sa dati:
```
python face_sorter.py "C:\Users\Ako\Pictures\Photos" --undo
```

## Cache at resume
Gumagawa ito ng `<photos folder>_Sorted_cache.pkl` katabi ng photos mo. Dahil dito:
- Pagkatapos ng `--dry-run`, mabilis na ang totoong sort (hindi na sinusuri ulit ang mukha).
- Pwedeng subukan ang iba't ibang `--threshold` nang mabilis.
- Kapag naputol (Ctrl+C, nag-shutdown), i-run lang ulit at itutuloy kung saan huminto.
Kusa itong mabubura pagkatapos ng totoong sort.

## Kung mali ang pag-group
- **Magkaibang tao, napasama sa iisang Face folder:** higpitan, hal. `--threshold 0.4`
- **Iisang tao, nahati sa ilang Face folder:** luwagan, hal. `--threshold 0.6`

Ang iba pang settings (min photos bawat mukha, laki ng mukha, atbp.) ay nasa taas ng `face_sorter.py`.
