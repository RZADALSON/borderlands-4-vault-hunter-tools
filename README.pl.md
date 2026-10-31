# Vault Hunter Tools

Filtr lootu i licznik DPS do Borderlands 4 w jednej aplikacji. Filtr ukrywa to, co Cię nie interesuje, albo zostawia wszystko na ziemi i mocno wyróżnia to, co chcesz. Licznik pokazuje w małym okienku obrażenia na sekundę. Ma instalator, więc nie trzeba samemu stawiać Python SDK.

[English](README.md)

## Instalacja

1. Pobierz `VaultHunterTools-Setup-*-PL.msi` z [Releases](../../releases).
2. Zamknij grę i uruchom instalator. Sprawdź wykryty folder gry albo wskaż ten z `Borderlands4.exe`.
3. Uruchom grę. Pierwszy start przygotowuje menu modów, a w prawym górnym rogu pojawi się prośba o restart.
4. Uruchom ją ponownie. F7 albo MODS w menu pauzy otwiera ustawienia.

Instalator nie jest podpisany, więc SmartScreen może ostrzec. Sumy SHA-256 są w opisie wydania.

Do folderu gry trafiają Python SDK, ta aplikacja i BL4 Mod Menu, a do Windows Microsoft Visual C++ Redistributable, jeśli go brakuje. Save'y i pliki gry zostają bez zmian. Starsza wersja zostanie podmieniona, a ustawienia filtra zostają. Dotyczy to też Borderlands 4 Loot Filter. Osobny Borderlands 4 DPS Meter zostanie usunięty, a ustawienia licznika wrócą do domyślnych.

## Co robi

- **Ukrywanie:** wybrane itemy znikają z ziemi. Nic nie jest usuwane, po wyłączeniu filtra wracają. Można filtrować po rzadkości, firmie, typie i postaci (mody klasowe), a także ukrywać amunicję według broni, zdrowie i inne pickupy.
- **Podświetlanie:** wypada wszystko, a wybrane itemy dostają dużo mocniejszy beam i znacznik na radarze.
- **Znaczniki na radarze gry** w kolorach rzadkości. Przy ukrywaniu pokazują sprzęt, który jeszcze leży.
- **Firmware:** wybierasz, który z 24 zestawów ma być zawsze widoczny albo podświetlony.
- **Napis** w prawym górnym rogu, gdy filtr działa, z liczbą ukrytych itemów i tym, ile sprzętu leży jeszcze do zebrania.

Ukrytych itemów nie da się podnieść, a to, co sam wyrzucisz z plecaka, zostaje widoczne. Obie rzeczy można wyłączyć.

Domyślnie ukrywane są itemy białe, zielone i niebieskie. Sprzęt z firmware, anointmentem i shiny zostaje widoczny, chyba że to zmienisz.

F8 wstrzymuje filtr. Menu jest po polsku lub angielsku, według języka gry. Wybór w `Język / Language` zostaje zapisany.

## Licznik DPS

Pokazuje DPS, sumę obrażeń, czas walki, udział krytyków, najlepsze trafienie, zabójstwa i wynik ostatniej walki. Gdy menu jest otwarte, chowa się. F6 go resetuje. Ustawienia są w menu pod `Licznik DPS`:

- **Liczenie DPS:** cała walka, czyli wszystkie obrażenia podzielone przez czas od pierwszego do ostatniego trafienia, albo tylko ostatnie 1 do 60 sekund.
- **Reset licznika:** domyślnie 5 sekund po ostatnim trafieniu, można ustawić od 1 do 60 sekund albo resetować tylko klawiszem F6. Gra nie jest pytana, czy wrogowie są w pobliżu, liczy się tylko to, kiedy kogoś ostatnio trafiłeś.
- **Obrażenia w czasie** i **obrażenia towarzyszy** są domyślnie liczone.
- **Wygląd licznika:** pięć stylów (domyślnie same liczby, czyli tylko pochylone niebieskie liczby jak obrażenia w grze, poza tym panel jak HUD gry, kompaktowy, sam tekst i neon), co pokazuje, gdzie stoi i jak jest duży.

Liczy tylko Twoje obrażenia. Działa solo i u hosta. Gościom w co-opie gra nie podaje obrażeń, więc licznik zostaje na zerze i mówi dlaczego.

Ustawienia, które przy Twoim wyborze nic nie zmieniają, są wyszarzone, także w filtrze.

## Pytania

**F7 otwiera prosty panel albo gra prosi o restart.** To normalne po instalacji, gra wczytuje pliki menu tylko przy starcie. Uruchom ją ponownie.

**Wyrzuciłem item i zniknął.** Wyrzucone rzeczy są rozpoznawane po ubytku w plecaku i itemie, który pojawia się obok Ciebie, więc to, co odkładasz z wyposażenia, może nie zostać rozpoznane. F8 pokazuje wszystko.

**Czemu widzę item, który powinien być ukryty?** Najczęściej przez wyjątek: firmware, anointment, shiny albo ochronę rzadkości. Można je wyłączyć.

**Patch coś zepsuł.** Log jest w `OakGame\Binaries\Win64\Plugins\unrealsdk.log`. Po patchu SDK może wymagać nowej wersji. Jeśli gra nie chce się uruchomić, odinstaluj filtr albo usuń `OakGame\Binaries\Win64\dsound.dll`.

## Odinstalowanie

Ustawienia Windows, Zainstalowane aplikacje, Vault Hunter Tools. Ustawienia modów i mody doinstalowane osobno zostają w `sdk_mods`.

Autorzy, licencje i budowanie są w [angielskim opisie](README.md).
