# Borderlands 4 Loot Filter

**English:** a loot filter for Borderlands 4 with an MSI installer. Download
`Borderlands4LootFilter-Setup-*-EN.msi` from [Releases](../../releases), close the game, run it and pick the game's
folder. Start the game, restart it when it asks you to, then press F7. The filter hides or highlights the items you
choose, and follows the game's language (Polish or English) unless you pick one under `Język / Language`.

Filtr lootu do Borderlands 4 z instalatorem MSI. Wskazujesz folder gry, a resztę instalator robi sam.

> **Status:** część funkcji nie była jeszcze sprawdzona w grze: wybór języka i angielskie menu (1.5.0), znaczniki na radarze
> gry, blokada podnoszenia, wykrywanie wyrzuconych itemów, filtr poziomu i aktualizacja przez ten instalator. Przed instalacją
> zamknij grę. Starsza wersja zostanie podmieniona, a Twoje ustawienia zostaną.

## Co potrafi

- **Ukrywanie:** wybrane itemy znikają z ziemi. Nic nie jest usuwane ani przenoszone, więc po wyłączeniu
  filtra wracają. Filtrować można po rzadkości, firmie, typie i postaci (mody klasowe), a także ukrywać amunicję,
  zdrowie i inne pickupy.
  Ukrytych itemów nie da się też podnieść, a to, co sam wyrzucisz z plecaka, zostaje widoczne (obie opcje można wyłączyć).
- **Radar gry:** znaczniki w kolorach rzadkości na radarze samej gry. Przy ukrywaniu pokazują sprzęt, który jeszcze leży.
- **Podświetlanie:** wypada wszystko, a wybrane itemy dostają mocniejszy beam i znacznik na radarze.
- **Poziom i amunicja:** ukrywanie sprzętu poniżej wybranego poziomu oraz amunicji do wybranych broni.
- **Wybór firmware:** decydujesz, który z 24 zestawów jest zawsze pokazywany lub podświetlany.
- **Napis `FILTR AKTYWNY`** w prawym górnym rogu, gdy filtr działa. Pokazuje też liczbę ukrytych itemów.
- **Ustawienia w grze:** F7 otwiera menu po polsku lub angielsku, zależnie od języka gry. Wybór w `Język / Language` zostaje
  zapisany. F8 chwilowo wstrzymuje filtr.

Domyślnie ukrywane są itemy białe, zielone i niebieskie. Sprzęt z firmware, anointmentem i shiny zawsze
zostaje widoczny, chyba że wyłączysz to w opcjach.

## Instalacja

1. Pobierz `Borderlands4LootFilter-Setup-*-PL.msi` z [Releases](../../releases).
2. Zamknij Borderlands 4 i uruchom instalator.
3. Sprawdź wykryty folder gry albo wskaż ten z plikiem `Borderlands4.exe`.
4. Uruchom grę. Pierwszy start przygotowuje menu, a w prawym górnym rogu pojawi się prośba o restart.
5. Uruchom grę ponownie. Teraz F7 albo pozycja **MODS** w menu pauzy otwiera pełne menu w interfejsie gry.

Instalator nie jest podpisany cyfrowo, więc Windows SmartScreen może pokazać ostrzeżenie. Sumę SHA-256
pliku znajdziesz w opisie wydania.

Instalator dodaje do folderu gry Python SDK, filtr i BL4 Mod Menu, a do systemu Microsoft Visual C++
Redistributable, jeśli go brakuje. Save'y nie są zmieniane, a pliki gry nie są podmieniane.

BL4 Mod Menu przy starcie gry pyta GitHuba o nowe wersje modów, ale niczego nie pobiera bez kliknięcia.
Można to wyłączyć w jego opcjach.

## Najczęstsze pytania

**Po instalacji F7 pokazuje prosty panel albo prośbę o restart.** To normalne przy pierwszym uruchomieniu: gra wczytuje
pliki menu tylko przy starcie. Uruchom ją ponownie.

**Czy można podnieść ukryty item?** Domyślnie nie, bo traci kolizję. Opcja `Blokuj podnoszenie ukrytych` to zmienia.

**Wyrzuciłem item i zniknął.** Wyrzucone z plecaka powinny zostać widoczne (`Pokazuj wyrzucone itemy`). Rozpoznawane są po
ubytku w plecaku i pojawieniu się itemu w pobliżu, więc to, co odkładasz z wyposażenia, może nie zostać rozpoznane. F8
pokazuje wszystko.

**Czemu widzę item, który powinien być ukryty?** Najczęściej przez wyjątek: firmware, anointment, shiny albo ochronę
rzadkości. Wyłączysz je w opcjach.

**Gra dostała patch i coś nie działa.** Log jest w `OakGame\Binaries\Win64\Plugins\unrealsdk.log`. Po patchu SDK może
wymagać nowej wersji. W razie problemów ze startem gry usuń `OakGame\Binaries\Win64\dsound.dll` lub odinstaluj mod.

## Odinstalowanie

Ustawienia Windows → Zainstalowane aplikacje → **Borderlands 4 Loot Filter**.
Twoje ustawienia modów i mody doinstalowane osobno zostają w folderze `sdk_mods`.

Po aktualizacji gry SDK może przestać działać, dopóki nie wyjdzie jego nowa wersja. Jeśli gra zacznie się
wywalać, odinstaluj mody albo usuń `OakGame\Binaries\Win64\dsound.dll`.

## Budowanie

Potrzebne są Python z Pillow, .NET SDK i .NET Framework 4.7.2 Targeting Pack.

```bash
dotnet tool install wix --tool-path installer/tools --version 5.0.2
python installer/build.py
```

Do `installer/vendor/` trzeba najpierw włożyć pliki, których nie ma w repozytorium:

| Plik | Skąd |
|---|---|
| `oak2-sdk.zip` | [oak2-mod-manager v0.3](https://github.com/bl-sdk/oak2-mod-manager/releases/tag/v0.3) |
| `bl4_mod_menu.sdkmod` | [bl4-fix v2026.10.29.1](https://github.com/flameaway/bl4-fix/releases/tag/v2026.10.29.1) |
| `vc_redist.x64.exe` | [Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| `GPL-3.0.txt`, `LGPL-3.0.txt`, `Python-LICENSE.txt`, `bl4-LICENSE.txt` | teksty licencji |

## Autorzy i licencje

Kod z tego repozytorium jest na licencji [GPL-3.0](LICENSE). Instalator zawiera też:

- [Oak2 Mod Manager](https://github.com/bl-sdk/oak2-mod-manager), [unrealsdk](https://github.com/bl-sdk/unrealsdk)
  i [pyunrealsdk](https://github.com/bl-sdk/pyunrealsdk): bl-sdk, LGPL-3.0.
- [BL4 Mod Menu](https://github.com/flameaway/bl4-fix): flameaway, GPL-3.0.
- Python: Python Software Foundation, licencja PSF.
- Microsoft Visual C++ Redistributable: warunki licencji Microsoftu.

Odczyt rzadkości z beamu jest zaadaptowany z [BL4 Loot Filter](https://github.com/jlangowells/bl4_loot_filter)
(Lango, GPL-3.0), który przypisuje oryginalną logikę SlippyCheeze. Palety kolorów i ścieżki itemów porównano
z [Loot Magnet](https://github.com/max0n4ik/LootMagnet). Na ekrany UMG wskazał wzorzec
[bl4-fix](https://github.com/flameaway/bl4-fix).

Tabela części firmware pochodzi z [bl4](https://github.com/monokrome/bl4) (monokrome, BSD-2-Clause).

Projekt nieoficjalny, niezwiązany z Gearbox ani 2K. Oprogramowanie jest dostarczane bez żadnej gwarancji.
