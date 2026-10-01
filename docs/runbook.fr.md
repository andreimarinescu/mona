# Aide-mémoire Mona (Claudiu)

Sur la machine Mona, dans un terminal, `mona` désigne `deploy/bin/mona` du dossier Mona.

## L'adresse
Ouvrez exactement l'adresse affichée par `mona doctor` sur la ligne **origin** (`MONA_PUBLIC_ORIGIN`). Toute autre écriture (`127.0.0.1` au lieu de `localhost`, un autre port) et chaque enregistrement est refusé avec « Not allowed ».

## Avant la présentation (T-10 min)
1. `mona doctor` -> toutes les lignes en GREEN. RED indique le problème (voir plus bas). AMBER fonctionne, mais notez-le.
2. `mona demo-reset --anchor today`, répondez `y`. Elle se termine par « done » et un doctor vert.
3. Navigateur sur Home, 1440 de large, anglais, clair. Vérifiez le projecteur.
4. Échauffement : dans Chat, posez « What is due this month? » et attendez la réponse (la première est la plus lente).
5. Téléphone prêt pour le document apporté par un participant.

## Démarrer et arrêter
- `mona stop` arrête tout ; `mona up` redémarre, attend que tout soit prêt, puis `mona doctor`.
- Bloqué ? `mona stop`, attendez 10 secondes, `mona up`. Documents et historique sont conservés.
- `mona demo-reset --prefiled` restaure la même journée avec le lot déjà classé (secours du temps 2).

## Répétition (Andrei)
`mona stage-build` reconstruit la scène de zéro. Pour garder un bon débrief : `mona demo-reset`, déposez le lot, jugez les questions ; si elles sont bonnes, `mona demo-snapshot --refresh-textcache --name demo`.

## Si Mona est hors ligne ou lente, temps par temps
| Temps | À faire |
|---|---|
| Meet Mona | Home en erreur : ouvrez le journal d'activité ; le résumé est calculé depuis la base |
| The pile | Traitement bloqué : `mona demo-reset --prefiled`, montrez le journal d'activité |
| Evidence | Surlignage manquant : lisez les citations dans le panneau latéral |
| Back to the pile | Lot inachevé : commentez les lignes en cours |
| Mona asks | Débrief de la répétition, en cache. Apply échoue : Rules › Disabled, activez la règle de cette question, vérifiez l'aperçu, Apply |
| Ask Mona | Modèle bloqué : montrez les mêmes réponses dans Archive et Activity |
| Volunteered document | Depuis le navigateur du téléphone vers Intake, « Visitor document » coché |
| Trust | Annulation en erreur : montrez les entrées du journal, chemins avant et après |
| Close | Les diapositives |

Machine injoignable : dites-le et présentez avec les diapositives ; le mode démo cloud (portable) se décide avec Andrei.

## Ce qu'il faut dire sur la confidentialité
« Le document et tout ce que Mona en a tiré sont supprimés au bout de 24 heures. » Cela couvre le fichier, les données extraites, les suggestions, les échéances et le journal. Une conversation à son sujet reste dans le chat. En conclusion : « Mona tourne sur cette machine ; rien ne sort du cabinet. » En mode démo cloud, dites-le et omettez cette phrase.

## Qui appeler
Andrei (sur place) : ____________ . Secours : ____________ .
