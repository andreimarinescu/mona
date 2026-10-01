# Aide-mémoire Mona (Claudiu)

Sur la machine Mona, dans un terminal, `mona` désigne la commande `deploy/bin/mona` du dossier Mona.

## L'adresse
Ouvrez exactement l'adresse affichée par `mona doctor` sur la ligne **origin** (`MONA_PUBLIC_ORIGIN`). Toute autre écriture (`127.0.0.1` au lieu de `localhost`, un autre port) et chaque enregistrement est refusé avec « Not allowed ».

## Avant la présentation (T-10 min)
1. `mona doctor` -> toutes les lignes en GREEN. RED indique le problème (voir plus bas). AMBER fonctionne, mais notez-le.
2. `mona demo-reset --anchor today`, répondez `y`. La commande se termine par « done » et un doctor vert.
3. Navigateur sur Home, 1440 de large, anglais, thème clair. Vérifiez le projecteur.
4. Échauffement : ouvrez Chat, posez une question (« What is due this month? ») et attendez la réponse. La première réponse est la plus lente.
5. Téléphone prêt pour le document apporté par un participant.

## Démarrer et arrêter
- `mona stop` arrête tout. `mona up` redémarre et attend que tout soit en bonne santé ; puis `mona doctor`.
- Bloqué ? `mona stop`, attendez 10 secondes, `mona up`. Les documents et l'historique sont conservés.
- `mona demo-reset --prefiled` restaure la même journée avec le lot déjà classé (secours du temps 2).

## Si Mona est hors ligne ou lente, temps par temps
| Temps | À faire |
|---|---|
| Meet Mona | Home en erreur : ouvrez le journal d'activité ; le résumé est calculé depuis la base |
| The pile | Traitement bloqué : `mona demo-reset --prefiled`, montrez le journal d'activité |
| Evidence | Surlignage manquant : lisez les citations dans le panneau latéral |
| Back to the pile | Lot inachevé : commentez les lignes en cours et poursuivez |
| Mona asks | Modèle lent : le débrief en cache s'affiche. Apply échoue : écran Rules, activez la règle, même aperçu |
| Ask Mona | Modèle bloqué : montrez les mêmes réponses dans Archive et Activity |
| Volunteered document | Envoi depuis le navigateur du téléphone vers Intake, case « Visitor document » cochée |
| Trust | Annulation en erreur : montrez les entrées du journal et leurs chemins avant et après |
| Close | Les diapositives |

Machine injoignable : dites-le à la salle et présentez avec les diapositives. Le mode démo cloud (ordinateur portable) est une décision d'Andrei.

## Ce qu'il faut dire sur la confidentialité
« Le document et tout ce que Mona en a tiré sont supprimés au bout de 24 heures. » Cela couvre le fichier, les données extraites, les suggestions, les échéances et le journal. Une conversation à son sujet reste dans le chat. En conclusion : « Mona tourne sur cette machine ; rien ne sort du cabinet. » En mode démo cloud, dites que c'est le mode démo cloud et omettez cette phrase.

## Qui appeler
Andrei (sur place) : ____________ . Secours : ____________ .
